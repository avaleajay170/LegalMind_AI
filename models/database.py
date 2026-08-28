from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import certifi
import os
from config import Config


# ── GLOBAL CLIENT ────────────────────────────────────────
_client = None
_db     = None


def get_db():
    """Get MongoDB database instance."""
    global _client, _db

    if _db is not None:
        return _db

    try:
        _client = MongoClient(
            Config.MONGO_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000
        )
        # Test connection
        _client.admin.command("ping")
        _db = _client[Config.MONGO_DB_NAME]
        print("✅ MongoDB connected successfully.")
        return _db

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print(f"❌ MongoDB connection failed: {e}")
        raise


def init_db():
    """Initialize collections and indexes."""
    db = get_db()

    # ── USERS ────────────────────────────────────────────
    db[Config.USERS_COLLECTION].create_index(
        [("email", ASCENDING)], unique=True
    )
    db[Config.USERS_COLLECTION].create_index(
        [("enrollment_no", ASCENDING)], unique=True
    )

    # ── CASES ────────────────────────────────────────────
    db[Config.CASES_COLLECTION].create_index(
        [("lawyer_id", ASCENDING)]
    )
    db[Config.CASES_COLLECTION].create_index(
        [("status", ASCENDING)]
    )

    # ── DEADLINES ────────────────────────────────────────
    db[Config.DEADLINES_COLLECTION].create_index(
        [("case_id", ASCENDING)]
    )
    db[Config.DEADLINES_COLLECTION].create_index(
        [("due_date", ASCENDING)]
    )

    # ── DOCUMENTS ────────────────────────────────────────
    db[Config.DOCUMENTS_COLLECTION].create_index(
        [("case_id", ASCENDING)]
    )

    # ── CHAT HISTORY ─────────────────────────────────────
    db[Config.CHAT_COLLECTION].create_index(
        [("case_id", ASCENDING), ("timestamp", ASCENDING)]
    )

    # ── SECTION SUGGESTIONS ──────────────────────────────
    db[Config.SECTIONS_COLLECTION].create_index(
        [("lawyer_id", ASCENDING)]
    )

    print("✅ MongoDB collections and indexes initialized.")


def close_db():
    """Close MongoDB connection."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db     = None
        print("MongoDB connection closed.")