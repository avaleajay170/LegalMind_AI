import os
import faiss
import pickle
import numpy as np
import google.generativeai as genai
from config import Config
from services.pdf_service import extract_text_from_pdf, chunk_text

# ── CONFIGURE GEMINI ──────────────────────────────────────
genai.configure(api_key=Config.GEMINI_API_KEY)

# ── PATHS ─────────────────────────────────────────────────
INDEX_PATH    = os.path.join(Config.VECTOR_STORE_PATH, "legal_index.faiss")
CHUNKS_PATH   = os.path.join(Config.VECTOR_STORE_PATH, "legal_chunks.pkl")
EMBED_DIM     = 768   # Gemini embedding dimension


# ── GET EMBEDDING ─────────────────────────────────────────
def get_embedding(text):
    """
    Get embedding vector for a text using Gemini.

    Args:
        text : input text string

    Returns:
        list of floats — embedding vector
    """
    try:
        result = genai.embed_content(
            model   = "models/embedding-001",
            content = text,
            task_type = "retrieval_document"
        )
        return result["embedding"]

    except Exception as e:
        print(f"❌ Embedding error: {e}")
        return None


# ── BUILD FAISS INDEX FROM PDFs ───────────────────────────
def build_index_from_pdfs(pdf_folder=None):
    """
    Build FAISS index from all PDFs in the data folder.
    Run this once to index IPC, CrPC, CPC, IT Act PDFs.

    Args:
        pdf_folder : path to folder containing legal PDFs

    Returns:
        bool — True if successful
    """
    if pdf_folder is None:
        pdf_folder = Config.DATA_FOLDER

    all_chunks = []

    # Extract text from all PDFs in data folder
    for filename in os.listdir(pdf_folder):
        if filename.endswith(".pdf"):
            filepath = os.path.join(pdf_folder, filename)
            print(f"📄 Processing: {filename}")

            text   = extract_text_from_pdf(filepath)
            chunks = chunk_text(
                text,
                chunk_size = Config.CHUNK_SIZE,
                overlap    = Config.CHUNK_OVERLAP
            )

            # Tag each chunk with source
            for chunk in chunks:
                all_chunks.append({
                    "text":   chunk,
                    "source": filename
                })

            print(f"   ✅ {len(chunks)} chunks extracted")

    if not all_chunks:
        print("❌ No chunks found. Add PDF files to data/ folder.")
        return False

    print(f"\n🔢 Total chunks: {len(all_chunks)}")
    print("⏳ Generating embeddings...")

    # Generate embeddings
    embeddings = []
    texts      = []

    for i, chunk in enumerate(all_chunks):
        embedding = get_embedding(chunk["text"])
        if embedding:
            embeddings.append(embedding)
            texts.append(chunk)
        if (i + 1) % 10 == 0:
            print(f"   Embedded {i + 1}/{len(all_chunks)} chunks")

    if not embeddings:
        print("❌ No embeddings generated.")
        return False

    # Build FAISS index
    vectors = np.array(embeddings, dtype="float32")
    index   = faiss.IndexFlatL2(EMBED_DIM)
    index.add(vectors)

    # Save index and chunks to disk
    os.makedirs(Config.VECTOR_STORE_PATH, exist_ok=True)
    faiss.write_index(index, INDEX_PATH)

    with open(CHUNKS_PATH, "wb") as f:
        pickle.dump(texts, f)

    print(f"\n✅ FAISS index built with {index.ntotal} vectors")
    print(f"   Saved to: {INDEX_PATH}")
    return True


# ── LOAD FAISS INDEX ──────────────────────────────────────
def load_index():
    """
    Load FAISS index and chunks from disk.

    Returns:
        tuple (index, chunks) or (None, None)
    """
    if not os.path.exists(INDEX_PATH) or \
       not os.path.exists(CHUNKS_PATH):
        print("⚠️ FAISS index not found. Run build_index_from_pdfs() first.")
        return None, None

    try:
        index = faiss.read_index(INDEX_PATH)

        with open(CHUNKS_PATH, "rb") as f:
            chunks = pickle.load(f)

        return index, chunks

    except Exception as e:
        print(f"❌ Error loading FAISS index: {e}")
        return None, None


# ── SEARCH LEGAL DOCS ─────────────────────────────────────
def search_legal_docs(query, top_k=None):
    """
    Search FAISS index for relevant legal content.

    Args:
        query : legal research query
        top_k : number of results to return

    Returns:
        str — concatenated relevant legal text
    """
    if top_k is None:
        top_k = Config.RAG_TOP_K

    # Load index
    index, chunks = load_index()

    if index is None:
        return "Legal document index not available. Please contact admin."

    # Get query embedding
    query_embedding = get_embedding(query)

    if query_embedding is None:
        return "Could not process query. Please try again."

    # Search FAISS
    query_vector = np.array([query_embedding], dtype="float32")
    distances, indices = index.search(query_vector, top_k)

    # Collect results
    results = []
    for i, idx in enumerate(indices[0]):
        if idx == -1:
            continue
        chunk = chunks[idx]
        results.append(
            f"[Source: {chunk['source']}]\n{chunk['text']}"
        )

    if not results:
        return "No relevant legal documents found for this query."

    return "\n\n---\n\n".join(results)


# ── ADD CASE DOCUMENT TO INDEX ────────────────────────────
def add_document_to_index(text, filename):
    """
    Add a single uploaded case document to the FAISS index.

    Args:
        text     : extracted text from uploaded PDF
        filename : name of the file

    Returns:
        bool — True if successful
    """
    try:
        chunks = chunk_text(
            text,
            chunk_size = Config.CHUNK_SIZE,
            overlap    = Config.CHUNK_OVERLAP
        )

        if not chunks:
            return False

        # Load existing index
        index, existing_chunks = load_index()

        if index is None:
            # Create new index if none exists
            index          = faiss.IndexFlatL2(EMBED_DIM)
            existing_chunks = []

        new_embeddings = []
        new_chunks     = []

        for chunk in chunks:
            embedding = get_embedding(chunk)
            if embedding:
                new_embeddings.append(embedding)
                new_chunks.append({
                    "text":   chunk,
                    "source": filename
                })

        if not new_embeddings:
            return False

        # Add to index
        vectors = np.array(new_embeddings, dtype="float32")
        index.add(vectors)
        existing_chunks.extend(new_chunks)

        # Save updated index
        faiss.write_index(index, INDEX_PATH)
        with open(CHUNKS_PATH, "wb") as f:
            pickle.dump(existing_chunks, f)

        print(f"✅ Added {len(new_chunks)} chunks from {filename}")
        return True

    except Exception as e:
        print(f"❌ Error adding document to index: {e}")
        return False


# ── CHECK IF INDEX EXISTS ─────────────────────────────────
def index_exists():
    """Check if FAISS index has been built."""
    return (
        os.path.exists(INDEX_PATH) and
        os.path.exists(CHUNKS_PATH)
    )


# ── INDEX STATS ───────────────────────────────────────────
def get_index_stats():
    """Return stats about the current FAISS index."""
    index, chunks = load_index()
    if index is None:
        return {"exists": False, "vectors": 0, "chunks": 0}

    return {
        "exists":  True,
        "vectors": index.ntotal,
        "chunks":  len(chunks)
    }