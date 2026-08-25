import os

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

from rag import HISTORY_TURNS, build_chain, get_vectorstore

load_dotenv()

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

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            st.caption("Sources: " + ", ".join(msg["sources"]))

question = st.chat_input("Ask a question about your documents...")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    chat_history = []
    for m in st.session_state.messages[:-1]:
        cls = HumanMessage if m["role"] == "user" else AIMessage
        chat_history.append(cls(content=m["content"]))
    chat_history = chat_history[-HISTORY_TURNS * 2:]

    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking..."):
                response = chain.invoke({"input": question, "chat_history": chat_history})
            answer = response["answer"]
            sources = sorted({d.metadata.get("source", "?") for d in response.get("context", [])})
            st.markdown(answer)
            if sources:
                st.caption("Sources: " + ", ".join(sources))
        except Exception as e:
            answer = f"Error: {e}"
            sources = []
            st.error(answer)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
    })
