import os
from dotenv import load_dotenv

load_dotenv()

class Config:

    # ── FLASK ───────────────────────────────────────────
    SECRET_KEY        = os.getenv("SECRET_KEY", "legalmind-secret-key-2024")
    FLASK_DEBUG       = os.getenv("FLASK_DEBUG", "True") == "True"

    # ── GEMINI API ──────────────────────────────────────
    GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL      = "gemini-1.5-flash"

    # ── MONGODB ─────────────────────────────────────────
    MONGO_URI         = os.getenv("MONGO_URI", "")
    MONGO_DB_NAME     = os.getenv("MONGO_DB_NAME", "legalmind_db")

    # ── COLLECTIONS ─────────────────────────────────────
    USERS_COLLECTION       = "users"
    CASES_COLLECTION       = "cases"
    DEADLINES_COLLECTION   = "deadlines"
    DOCUMENTS_COLLECTION   = "documents"
    CHAT_COLLECTION        = "chat_history"
    SECTIONS_COLLECTION    = "section_suggestions"

    # ── FOLDERS ─────────────────────────────────────────
    UPLOAD_FOLDER     = os.getenv("UPLOAD_FOLDER",    "uploads")
    GENERATED_FOLDER  = os.getenv("GENERATED_FOLDER", "generated")
    VECTOR_STORE_PATH = "vector_store/faiss_index"
    DATA_FOLDER       = "data"

    # ── FILE UPLOAD ─────────────────────────────────────
    MAX_CONTENT_LENGTH  = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS  = {"pdf", "doc", "docx", "txt"}

    # ── ADVOCATE REGISTRY ───────────────────────────────
    REGISTRY_PATH     = os.path.join("data", "advocate_registry.json")

    # ── RAG SETTINGS ────────────────────────────────────
    CHUNK_SIZE        = 1000
    CHUNK_OVERLAP     = 200
    RAG_TOP_K         = 4

    # ── DOCUMENT TEMPLATES ──────────────────────────────
    TEMPLATES = [
        "Legal Notice",
        "FIR Draft",
        "Affidavit",
        "Bail Application",
        "Contract Agreement"
    ]