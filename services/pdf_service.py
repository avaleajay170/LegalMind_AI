import fitz          # PyMuPDF
import pdfplumber
import os


# ── EXTRACT TEXT USING PyMuPDF ────────────────────────────
def extract_text_pymupdf(filepath):
    """
    Extract text from PDF using PyMuPDF (fitz).
    Fast and handles most standard PDFs.

    Returns:
        str — extracted text
    """
    try:
        text = ""
        doc  = fitz.open(filepath)

        for page_num in range(len(doc)):
            page  = doc[page_num]
            text += f"\n--- Page {page_num + 1} ---\n"
            text += page.get_text("text")

        doc.close()
        return text.strip()

    except Exception as e:
        print(f"❌ PyMuPDF extraction error: {e}")
        return ""


# ── EXTRACT TEXT USING PDFPLUMBER ─────────────────────────
def extract_text_pdfplumber(filepath):
    """
    Extract text from PDF using pdfplumber.
    Better for PDFs with tables and complex layouts.

    Returns:
        str — extracted text
    """
    try:
        text = ""
        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text += f"\n--- Page {page_num + 1} ---\n"
                page_text = page.extract_text()
                if page_text:
                    text += page_text

        return text.strip()

    except Exception as e:
        print(f"❌ pdfplumber extraction error: {e}")
        return ""


# ── MAIN EXTRACT FUNCTION ─────────────────────────────────
def extract_text_from_pdf(filepath):
    """
    Extract text from PDF.
    Tries PyMuPDF first, falls back to pdfplumber.

    Args:
        filepath : full path to the PDF file

    Returns:
        str — extracted text or empty string
    """
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return ""

    if not filepath.lower().endswith(".pdf"):
        return ""

    # Try PyMuPDF first
    text = extract_text_pymupdf(filepath)

    # If PyMuPDF got very little text, try pdfplumber
    if len(text.strip()) < 100:
        print("⚠️ PyMuPDF got little text, trying pdfplumber...")
        text = extract_text_pdfplumber(filepath)

    if not text.strip():
        return "Could not extract text from this PDF. It may be scanned or image-based."

    return text


# ── EXTRACT METADATA ──────────────────────────────────────
def extract_pdf_metadata(filepath):
    """
    Extract metadata from PDF — title, author, pages etc.

    Returns:
        dict — metadata
    """
    try:
        doc      = fitz.open(filepath)
        metadata = doc.metadata
        pages    = len(doc)
        doc.close()

        return {
            "title":    metadata.get("title",    "Unknown"),
            "author":   metadata.get("author",   "Unknown"),
            "pages":    pages,
            "format":   metadata.get("format",   "PDF"),
            "producer": metadata.get("producer", "Unknown")
        }

    except Exception as e:
        print(f"❌ Metadata extraction error: {e}")
        return {
            "title":  "Unknown",
            "author": "Unknown",
            "pages":  0
        }


# ── CHUNK TEXT FOR FAISS ──────────────────────────────────
def chunk_text(text, chunk_size=1000, overlap=200):
    """
    Split extracted text into overlapping chunks
    for FAISS embedding.

    Args:
        text       : full extracted text
        chunk_size : characters per chunk
        overlap    : overlap between chunks

    Returns:
        list of str — text chunks
    """
    if not text:
        return []

    chunks = []
    start  = 0

    while start < len(text):
        end   = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap

    return chunks


# ── GET PAGE COUNT ────────────────────────────────────────
def get_page_count(filepath):
    """Return number of pages in a PDF."""
    try:
        doc   = fitz.open(filepath)
        pages = len(doc)
        doc.close()
        return pages
    except Exception:
        return 0
