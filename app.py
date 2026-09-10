import os
import time

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

from rag import HISTORY_TURNS, answer_question, build_chain, get_vectorstore

load_dotenv()

# Per-session rate limit. In-memory and per-process - resets on restart and
# doesn't share state across multiple app instances. Fine for a single
# small-team deployment; a multi-instance rollout needs a shared store
# (Redis) instead.
RATE_LIMIT_MAX_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 3600

st.set_page_config(page_title="RAG Assistant", page_icon="📄", layout="centered")
st.title("📄 RAG Assistant")
st.caption("Ask questions about the documents in `docs/`.")

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error("`ANTHROPIC_API_KEY` is not set. Add it to your `.env` file and restart.")
    st.stop()


@st.cache_resource(show_spinner="Indexing documents...")
def load_chain():
    vectorstore = get_vectorstore()
    if vectorstore is None:
        return None
    return build_chain(vectorstore)


with st.sidebar:
    st.header("Documents")
    st.caption("Add, edit, or remove files in `docs/`, then sync.")
    if st.button("🔄 Sync documents"):
        load_chain.clear()
        st.rerun()

chain = load_chain()
if chain is None:
    st.warning("No documents found. Add PDFs, `.txt`, `.md`, or `.docx` files to the "
               "`docs/` folder, then click **Sync documents**.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []  # [{"role", "content", "sources"}]
if "request_times" not in st.session_state:
    st.session_state.request_times = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            st.caption("Sources: " + ", ".join(msg["sources"]))

question = st.chat_input("Ask a question about your documents...")
if question:
    now = time.time()
    st.session_state.request_times = [
        t for t in st.session_state.request_times if now - t < RATE_LIMIT_WINDOW_SECONDS
    ]

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    if len(st.session_state.request_times) >= RATE_LIMIT_MAX_REQUESTS:
        answer = (f"Rate limit reached ({RATE_LIMIT_MAX_REQUESTS} questions per "
                  f"hour). Please try again later.")
        sources = []
        with st.chat_message("assistant"):
            st.error(answer)
    else:
        st.session_state.request_times.append(now)

        chat_history = []
        for m in st.session_state.messages[:-1]:
            cls = HumanMessage if m["role"] == "user" else AIMessage
            chat_history.append(cls(content=m["content"]))
        chat_history = chat_history[-HISTORY_TURNS * 2:]

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = answer_question(chain, question, chat_history)
            answer = response["answer"]
            sources = sorted(response["sources_used"])
            guardrail = response["guardrail"] or ""
            # Every stage that failed closed renders as a visible error rather
            # than as an answer, so a degraded pipeline can't look like a
            # confident result.
            if guardrail.startswith(("api_error", "retrieval_error", "generation_error")):
                st.error(answer)
            elif guardrail.startswith("output_blocked"):
                st.error(answer)
                st.caption("Blocked by the output scanner.")
            else:
                st.markdown(answer)
                if sources:
                    st.caption("Sources: " + ", ".join(sources))
                if "output_flagged:" in guardrail:
                    st.warning("Output scanner flagged this answer: "
                               + guardrail.split("output_flagged:", 1)[1])

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
    })
