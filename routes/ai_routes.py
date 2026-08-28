from flask import (
    Blueprint, render_template, request,
    session, jsonify, redirect, url_for
)
from datetime import datetime
from bson import ObjectId

from models.database import get_db
from config import Config
from routes.auth import login_required
from services.gemini_service    import ask_gemini
from services.rag_service       import search_legal_docs
from services.section_suggester import suggest_sections
from services.doc_generator     import generate_document
from services.risk_scorer       import calculate_risk_score

ai_bp = Blueprint("ai", __name__)


# ── AI CASE ASSISTANT — CHAT ──────────────────────────────
@ai_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    data      = request.get_json()
    case_id   = data.get("case_id", "").strip()
    message   = data.get("message", "").strip()

    if not case_id or not message:
        return jsonify({
            "success": False,
            "message": "Case ID and message are required."
        })

    db   = get_db()

    # Get case context
    case = db[Config.CASES_COLLECTION].find_one(
        {"_id": ObjectId(case_id)}
    )

    if not case:
        return jsonify({
            "success": False,
            "message": "Case not found."
        })

    # Get last 10 chat messages for context
    history = list(db[Config.CHAT_COLLECTION].find(
        {"case_id": case_id}
    ).sort("timestamp", -1).limit(10))
    history.reverse()

    # Build conversation history for Gemini
    chat_history = []
    for h in history:
        chat_history.append({
            "role":    h["role"],
            "content": h["message"]
        })

    # Build case context for system prompt
    case_context = f"""
    Case Title     : {case.get('title', '')}
    Client Name    : {case.get('client_name', '')}
    Case Type      : {case.get('case_type', '')}
    Court          : {case.get('court_name', '')}
    Status         : {case.get('status', '')}
    Description    : {case.get('description', '')}
    Risk Score     : {case.get('risk_score', 0)} / 100
    """

    # Get AI response
    response = ask_gemini(
        message      = message,
        case_context = case_context,
        history      = chat_history,
        mode         = "chat"
    )

    # Save user message to MongoDB
    db[Config.CHAT_COLLECTION].insert_one({
        "case_id":   case_id,
        "lawyer_id": session["lawyer_id"],
        "role":      "user",
        "message":   message,
        "timestamp": datetime.utcnow()
    })

    # Save AI response to MongoDB
    db[Config.CHAT_COLLECTION].insert_one({
        "case_id":   case_id,
        "lawyer_id": session["lawyer_id"],
        "role":      "assistant",
        "message":   response,
        "timestamp": datetime.utcnow()
    })

    return jsonify({
        "success":  True,
        "response": response
    })


# ── LEGAL RESEARCH ────────────────────────────────────────
@ai_bp.route("/research", methods=["GET", "POST"])
@login_required
def research():
    if request.method == "GET":
        return render_template("research.html")

    data  = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({
            "success": False,
            "message": "Please enter a research query."
        })

    # Search FAISS index
    context = search_legal_docs(query)

    # Ask Gemini with retrieved context
    response = ask_gemini(
        message      = query,
        case_context = context,
        history      = [],
        mode         = "research"
    )

    return jsonify({
        "success":  True,
        "response": response,
        "context":  context[:500] + "..." if len(context) > 500 else context
    })


# ── DOCUMENT DRAFTER ──────────────────────────────────────
@ai_bp.route("/draft", methods=["GET", "POST"])
@login_required
def draft():
    db = get_db()

    if request.method == "GET":
        # Get all cases for dropdown
        cases = list(db[Config.CASES_COLLECTION].find(
            {
                "lawyer_id": session["lawyer_id"],
                "status":    {"$ne": "archived"}
            }
        ))
        for c in cases:
            c["_id"] = str(c["_id"])

        return render_template(
            "drafter.html",
            cases     = cases,
            templates = Config.TEMPLATES
        )

    data          = request.get_json()
    case_id       = data.get("case_id", "").strip()
    template_type = data.get("template_type", "").strip()

    if not case_id or not template_type:
        return jsonify({
            "success": False,
            "message": "Case and template type are required."
        })

    # Get case data
    case = db[Config.CASES_COLLECTION].find_one(
        {"_id": ObjectId(case_id)}
    )

    if not case:
        return jsonify({
            "success": False,
            "message": "Case not found."
        })

    # Generate document
    result = generate_document(
        template_type = template_type,
        case          = case,
        lawyer_name   = session["lawyer_name"],
        enrollment_no = session["enrollment_no"]
    )

    if result["success"]:
        # Save generated doc to MongoDB
        db[Config.DOCUMENTS_COLLECTION].insert_one({
            "case_id":        case_id,
            "lawyer_id":      session["lawyer_id"],
            "filename":       result["filename"],
            "original_name":  result["filename"],
            "filepath":       result["filepath"],
            "doc_type":       "generated",
            "extracted_text": "",
            "file_size":      0,
            "uploaded_at":    datetime.utcnow()
        })

    return jsonify(result)


# ── SECTION SUGGESTER ─────────────────────────────────────
@ai_bp.route("/suggest-sections", methods=["GET", "POST"])
@login_required
def suggest_sections_route():
    db = get_db()

    if request.method == "GET":
        # Get cases for optional linking
        cases = list(db[Config.CASES_COLLECTION].find(
            {
                "lawyer_id": session["lawyer_id"],
                "status":    {"$ne": "archived"}
            }
        ))
        for c in cases:
            c["_id"] = str(c["_id"])

        return render_template(
            "section_suggester.html",
            cases = cases
        )

    data            = request.get_json()
    incident_text   = data.get("incident_text", "").strip()
    case_id         = data.get("case_id", "").strip()

    if not incident_text:
        return jsonify({
            "success": False,
            "message": "Please describe the incident."
        })

    if len(incident_text) < 20:
        return jsonify({
            "success": False,
            "message": "Please provide more detail about the incident."
        })

    # Get AI section suggestions
    result = suggest_sections(incident_text)

    if result["success"]:
        # Save to MongoDB
        db[Config.SECTIONS_COLLECTION].insert_one({
            "case_id":            case_id or None,
            "lawyer_id":          session["lawyer_id"],
            "incident_text":      incident_text,
            "primary_sections":   result["data"].get("primary_sections",   []),
            "supporting_sections":result["data"].get("supporting_sections", []),
            "bailable":           result["data"].get("bailable",           None),
            "cognizable":         result["data"].get("cognizable",         None),
            "court_type":         result["data"].get("court",              ""),
            "fir_type":           result["data"].get("fir_type",           ""),
            "next_steps":         result["data"].get("next_steps",         []),
            "created_at":         datetime.utcnow()
        })

    return jsonify(result)


# ── RISK SCORING ──────────────────────────────────────────
@ai_bp.route("/risk-score/<case_id>", methods=["GET"])
@login_required
def risk_score(case_id):
    db   = get_db()

    case = db[Config.CASES_COLLECTION].find_one(
        {"_id": ObjectId(case_id)}
    )

    if not case:
        return jsonify({
            "success": False,
            "message": "Case not found."
        })

    # Get deadlines and documents for scoring
    deadlines = list(db[Config.DEADLINES_COLLECTION].find(
        {"case_id": case_id, "is_done": False}
    ))

    documents = list(db[Config.DOCUMENTS_COLLECTION].find(
        {"case_id": case_id}
    ))

    # Calculate risk score
    result = calculate_risk_score(
        case      = case,
        deadlines = deadlines,
        documents = documents
    )

    if result["success"]:
        # Update risk score in MongoDB
        db[Config.CASES_COLLECTION].update_one(
            {"_id": ObjectId(case_id)},
            {"$set": {"risk_score": result["score"]}}
        )

    return jsonify(result)


# ── CHAT HISTORY ──────────────────────────────────────────
@ai_bp.route("/chat-history/<case_id>", methods=["GET"])
@login_required
def chat_history(case_id):
    db   = get_db()
    chats = list(db[Config.CHAT_COLLECTION].find(
        {"case_id": case_id}
    ).sort("timestamp", 1))

    result = []
    for chat in chats:
        result.append({
            "role":      chat["role"],
            "message":   chat["message"],
            "timestamp": chat["timestamp"].strftime("%H:%M")
        })

    return jsonify(result)


# ── CLEAR CHAT HISTORY ────────────────────────────────────
@ai_bp.route("/clear-chat/<case_id>", methods=["POST"])
@login_required
def clear_chat(case_id):
    db = get_db()
    db[Config.CHAT_COLLECTION].delete_many(
        {"case_id": case_id}
    )
    return jsonify({
        "success": True,
        "message": "Chat history cleared."
    })