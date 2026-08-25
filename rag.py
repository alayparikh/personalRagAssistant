import argparse
import hashlib
import json
import os
import re
import sys

import yaml

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains.history_aware_retriever import create_history_aware_retriever
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from docx import Document as DocxDocument
from docx.oxml.ns import qn
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DOCS_PATH = "./docs"
PERSIST_PATH = "./chroma_db"
MANIFEST_PATH = os.path.join(PERSIST_PATH, "manifest.json")
PERMISSIONS_PATH = "./permissions.yaml"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL = "claude-sonnet-5"
HISTORY_TURNS = 10  # remember last 10 exchanges
SUPERUSER_GROUP = "ALL"  # bypasses document filtering entirely


# Load the folder -> allowed-groups mapping used to tag each chunk on ingest
def load_permissions():
    if not os.path.exists(PERMISSIONS_PATH):
        return {}, ["Everyone"]
    with open(PERMISSIONS_PATH) as f:
        config = yaml.safe_load(f) or {}
    return config.get("folders", {}), config.get("default_groups", ["Everyone"])


def _normalize_path(path):
    return path[2:] if path.startswith("./") else path


# Which groups can see this file - the longest matching folder prefix wins,
# falling back to default_groups for anything not under a listed folder.
def groups_for_path(path, folder_map, default_groups):
    normalized = _normalize_path(path)
    best_match = None
    for folder in folder_map:
        folder_norm = _normalize_path(folder).rstrip("/")
        if normalized == folder_norm or normalized.startswith(folder_norm + "/"):
            if best_match is None or len(folder_norm) > len(best_match):
                best_match = folder_norm
    return folder_map[best_match] if best_match is not None else default_groups


# Build the Chroma metadata filter for a user's groups. None means no
# restriction (superuser or unauthenticated CLI use); an empty group list
# denies everything (fails closed) rather than matching everything.
def build_group_filter(allowed_groups):
    if allowed_groups is None or SUPERUSER_GROUP in allowed_groups:
        return None
    if not allowed_groups:
        return {"group___none__": True}  # matches no real chunk
    conditions = [{f"group_{g}": True} for g in allowed_groups]
    return conditions[0] if len(conditions) == 1 else {"$or": conditions}


# List eligible files under docs/ (skips hidden files, filters by extension)
def discover_files():
    if not os.path.isdir(DOCS_PATH):
        os.makedirs(DOCS_PATH, exist_ok=True)
        print("Created docs/ folder. Add your PDFs and text files there.")
        return []

    paths = []
    for root, _, files in os.walk(DOCS_PATH):
        for file in sorted(files):
            if file.startswith("."):  # .DS_Store, AppleDouble ._ files
                continue
            ext = os.path.splitext(file)[1].lower()
            if ext in (".pdf", ".txt", ".md", ".docx"):
                paths.append(os.path.join(root, file))

    return sorted(paths)


# Extract a paragraph's text with hyperlink targets inlined, e.g. a run
# reading "LinkedIn" that links to https://linkedin.com/in/x becomes
# "LinkedIn (https://linkedin.com/in/x)". Plain-text extraction (docx2txt,
# python-docx's .text) only sees the anchor text - the actual URL lives in
# the document's relationship table and is otherwise lost entirely.
def _paragraph_text_with_links(paragraph, rels):
    parts = []
    for child in paragraph._p:
        if child.tag == qn("w:hyperlink"):
            text = "".join(t.text or "" for t in child.iter(qn("w:t")))
            r_id = child.get(qn("r:id"))
            url = rels[r_id].target_ref if r_id in rels else None
            parts.append(f"{text} ({url})" if url and text else text)
        elif child.tag == qn("w:r"):
            parts.append("".join(t.text or "" for t in child.iter(qn("w:t"))))
    return "".join(parts)


def load_docx(path):
    document = DocxDocument(path)
    rels = document.part.rels

    lines = [_paragraph_text_with_links(p, rels) for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                lines.extend(_paragraph_text_with_links(p, rels) for p in cell.paragraphs)

    text = "\n".join(line for line in lines if line.strip())
    return [Document(page_content=text, metadata={"source": path})]


# Load a single file's contents, using the loader for its extension
def load_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        loader = PyPDFLoader(path)
    elif ext == ".docx":
        return load_docx(path)
    else:
        loader = TextLoader(path, autodetect_encoding=True)
    return loader.load()


def file_hash(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {}


def save_manifest(manifest):
    os.makedirs(PERSIST_PATH, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


# Split documents into chunks
def split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    return splitter.split_documents(documents)


def get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


# Re-embed only files that are new or whose content changed since the last
# run, and drop chunks for files that were removed. Unchanged files are
# never re-read or re-embedded.
def sync_vectorstore(store):
    current_files = discover_files()
    current_hashes = {path: file_hash(path) for path in current_files}

    manifest = load_manifest()
    changed_or_new = [p for p in current_hashes if manifest.get(p) != current_hashes[p]]
    removed = [p for p in manifest if p not in current_hashes]

    if not changed_or_new and not removed:
        print(f"Index up to date ({store._collection.count()} chunks).")
        return

    for path in removed + changed_or_new:
        store.delete(where={"source": path})

    folder_map, default_groups = load_permissions()

    added_chunks = 0
    for path in changed_or_new:
        documents = load_file(path)
        chunks = split_documents(documents)
        groups = groups_for_path(path, folder_map, default_groups)
        for chunk in chunks:
            for group in groups:
                chunk.metadata[f"group_{group}"] = True
        if chunks:
            store.add_documents(chunks)
        added_chunks += len(chunks)

    manifest = current_hashes
    save_manifest(manifest)

    print(f"Synced index: {len(changed_or_new)} new/updated file(s) "
          f"({added_chunks} chunks), {len(removed)} removed file(s). "
          f"Total: {store._collection.count()} chunks.")


# Open the persisted vector store and bring it up to date with docs/
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

    sync_vectorstore(store)

    if store._collection.count() == 0:
        return None
    return store


# BM25's default tokenizer just splits on whitespace, so a URL like
# "https://www.linkedin.com/in/x" is one opaque token that never matches a
# query for "linkedin" - every doc scores 0 and results become arbitrary.
# Splitting on non-alphanumeric characters breaks URLs/emails into real,
# matchable terms (linkedin, com, gmail, ...).
def _tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


# Combine vector similarity search with BM25 keyword search, both scoped to
# the given groups (None = unrestricted). Vector search alone misses short,
# dense chunks (headers, contact lines, links) that get outscored by
# longer, unrelated chunks; BM25 catches literal terms (names, emails,
# "linkedin"/"github") that vector search keeps losing.
def build_retriever(vectorstore, allowed_groups=None):
    where_filter = build_group_filter(allowed_groups)

    get_kwargs = {"include": ["documents", "metadatas"]}
    if where_filter:
        get_kwargs["where"] = where_filter
    raw = vectorstore.get(**get_kwargs)
    all_chunks = [
        Document(page_content=doc, metadata=meta)
        for doc, meta in zip(raw["documents"], raw["metadatas"])
    ]

    search_kwargs = {"k": 4}
    if where_filter:
        search_kwargs["filter"] = where_filter
    vector_retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)

    if not all_chunks:
        return vector_retriever  # same filter applied, so this also yields nothing

    bm25_retriever = BM25Retriever.from_documents(all_chunks, preprocess_func=_tokenize)
    bm25_retriever.k = 4

    return EnsembleRetriever(retrievers=[vector_retriever, bm25_retriever], weights=[0.5, 0.5])


# Build the chat chain: rewrite the question using history, then answer from context.
# allowed_groups scopes retrieval to what that user is permitted to see;
# None means unrestricted (CLI/local admin use).
def build_chain(vectorstore, allowed_groups=None):
    llm = ChatAnthropic(
        model=MODEL,
        max_tokens=16000,
    )

    retriever = build_retriever(vectorstore, allowed_groups)

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
                        help="delete and rebuild the vector store (--cli mode only; "
                             "the web UI has a Sync button instead)")
    parser.add_argument("--cli", action="store_true",
                        help="use the terminal chat instead of the web UI")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Add it to .env and try again.")
        return 1

    if not args.cli:
        import subprocess
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        return subprocess.call([sys.executable, "-m", "streamlit", "run", app_path])

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
