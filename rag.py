import argparse
import os
import sys

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains.history_aware_retriever import create_history_aware_retriever
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DOCS_PATH = "./docs"
PERSIST_PATH = "./chroma_db"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL = "claude-sonnet-5"
HISTORY_TURNS = 10  # remember last 10 exchanges


# Load documents from the docs/ folder
def load_documents():
    if not os.path.isdir(DOCS_PATH):
        os.makedirs(DOCS_PATH, exist_ok=True)
        print("Created docs/ folder. Add your PDFs and text files there.")
        return []

    documents = []
    for root, _, files in os.walk(DOCS_PATH):
        for file in sorted(files):
            if file.startswith("."):  # .DS_Store, AppleDouble ._ files
                continue

            path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()

            if ext == ".pdf":
                loader = PyPDFLoader(path)
            elif ext in (".txt", ".md"):
                loader = TextLoader(path, autodetect_encoding=True)
            else:
                continue

            # One unreadable file should not abort the whole ingest.
            try:
                documents.extend(loader.load())
            except Exception as e:
                print(f"Skipped {path}: {type(e).__name__}: {e}")

    return documents


# Split documents into chunks
def split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    return splitter.split_documents(documents)


def get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


# Open the persisted vector store, or build it from docs/ if it is missing
def get_vectorstore(reindex=False):
    embeddings = get_embeddings()

    if reindex and os.path.isdir(PERSIST_PATH):
        import shutil
        shutil.rmtree(PERSIST_PATH)

    store = Chroma(
        embedding_function=embeddings,
        persist_directory=PERSIST_PATH,
        collection_name="docs",
    )

    if store._collection.count() > 0:
        print(f"Using existing index ({store._collection.count()} chunks). "
              f"Run with --reindex to rebuild.")
        return store

    print("Loading documents...")
    documents = load_documents()
    if not documents:
        return None

    print(f"Loaded {len(documents)} pages/documents")
    chunks = split_documents(documents)
    print(f"Split into {len(chunks)} chunks")

    store.add_documents(chunks)
    print("Vector store created")
    return store


# Build the chat chain: rewrite the question using history, then answer from context
def build_chain(vectorstore):
    llm = ChatAnthropic(
        model=MODEL,
        max_tokens=16000,
    )

    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    contextualize_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "Given the chat history and the latest user question, rewrite the "
         "question so it can be understood on its own. Do NOT answer it; "
         "return the question unchanged if it is already self-contained."),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_prompt
    )

    answer_prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You answer questions using only the retrieved context below. "
         "If the context does not contain the answer, say so instead of "
         "guessing.\n\nContext:\n{context}"),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])
    answer_chain = create_stuff_documents_chain(llm, answer_prompt)

    return create_retrieval_chain(history_aware_retriever, answer_chain)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="RAG assistant over ./docs")
    parser.add_argument("--reindex", action="store_true",
                        help="delete and rebuild the vector store")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Export it and try again.")
        return 1

    vectorstore = get_vectorstore(reindex=args.reindex)
    if vectorstore is None:
        print("No documents found. Add files to the docs/ folder and try again.")
        return 1

    chain = build_chain(vectorstore)
    chat_history = []

    print("\nRAG Assistant ready. Type your questions (type 'quit' to exit):\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in ["quit", "exit", "q"]:
            break

        response = chain.invoke({"input": question, "chat_history": chat_history})
        print(f"\nAssistant: {response['answer']}\n")

        sources = {d.metadata.get("source", "?") for d in response.get("context", [])}
        if sources:
            print(f"Sources: {', '.join(sorted(sources))}\n")

        chat_history.extend([
            HumanMessage(content=question),
            AIMessage(content=response["answer"]),
        ])
        chat_history[:] = chat_history[-HISTORY_TURNS * 2:]

    return 0


if __name__ == "__main__":
    sys.exit(main())
