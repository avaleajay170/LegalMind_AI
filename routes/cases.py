from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash, jsonify
)
from datetime import datetime
from bson import ObjectId

from models.database import get_db
from config import Config
from routes.auth import login_required

cases_bp = Blueprint("cases", __name__)


# ── HELPER ───────────────────────────────────────────────
def get_urgency(due_date_str):
    """Return urgency level based on due date."""
    try:
        due  = datetime.strptime(due_date_str, "%Y-%m-%d")
        diff = (due - datetime.utcnow()).days
        if diff < 0:
            return "red"
        elif diff <= 3:
            return "amber"
        else:
            return "green"
    except Exception:
        return "green"


# ── DASHBOARD ────────────────────────────────────────────
@cases_bp.route("/dashboard")
@login_required
def dashboard():
    db        = get_db()
    lawyer_id = session["lawyer_id"]

    # Get all cases for this lawyer
    cases = list(db[Config.CASES_COLLECTION].find(
        {"lawyer_id": lawyer_id, "status": {"$ne": "archived"}}
    ).sort("created_at", -1))

    # Attach next deadline to each case
    for case in cases:
        case["_id"] = str(case["_id"])
        next_dl = db[Config.DEADLINES_COLLECTION].find_one(
            {
                "case_id": case["_id"],
                "is_done": False
            },
            sort=[("due_date", 1)]
        )
        case["next_deadline"] = next_dl if next_dl else None

    # Get upcoming deadlines (next 7 days) across all cases
    all_case_ids = [c["_id"] for c in cases]
    upcoming = list(db[Config.DEADLINES_COLLECTION].find(
        {
            "case_id": {"$in": all_case_ids},
            "is_done": False
        }
    ).sort("due_date", 1).limit(5))

    # Stats for dashboard
    stats = {
        "total_cases":    len(cases),
        "active_cases":   sum(1 for c in cases if c.get("status") == "active"),
        "high_risk":      sum(1 for c in cases if c.get("risk_score", 0) >= 70),
        "upcoming_count": len(upcoming)
    }

    return render_template(
        "dashboard.html",
        cases    = cases,
        upcoming = upcoming,
        stats    = stats
    )


# ── CREATE CASE ───────────────────────────────────────────
@cases_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_case():
    if request.method == "POST":
        title          = request.form.get("title", "").strip()
        client_name    = request.form.get("client_name", "").strip()
        client_phone   = request.form.get("client_phone", "").strip()
        client_email   = request.form.get("client_email", "").strip()
        case_type      = request.form.get("case_type", "").strip()
        court_name     = request.form.get("court_name", "").strip()
        description    = request.form.get("description", "").strip()

        if not title or not client_name or not case_type:
            flash("Title, client name and case type are required.", "error")
            return render_template("create_case.html")

        db       = get_db()
        new_case = {
            "lawyer_id":    session["lawyer_id"],
            "title":        title,
            "client_name":  client_name,
            "client_phone": client_phone,
            "client_email": client_email,
            "case_type":    case_type,
            "court_name":   court_name,
            "description":  description,
            "status":       "active",
            "risk_score":   0,
            "created_at":   datetime.utcnow(),
            "updated_at":   datetime.utcnow()
        }

        result = db[Config.CASES_COLLECTION].insert_one(new_case)
        flash(f"Case '{title}' created successfully!", "success")
        return redirect(url_for("cases.case_detail",
                                case_id=str(result.inserted_id)))

    return render_template("create_case.html")


# ── CASE DETAIL ───────────────────────────────────────────
@cases_bp.route("/<case_id>")
@login_required
def case_detail(case_id):
    db = get_db()

    # Get case
    case = db[Config.CASES_COLLECTION].find_one({
        "_id":       ObjectId(case_id),
        "lawyer_id": session["lawyer_id"]
    })

    if not case:
        flash("Case not found.", "error")
        return redirect(url_for("cases.dashboard"))

    case["_id"] = str(case["_id"])

    # Get deadlines
    deadlines = list(db[Config.DEADLINES_COLLECTION].find(
        {"case_id": case_id}
    ).sort("due_date", 1))

    # Get documents
    documents = list(db[Config.DOCUMENTS_COLLECTION].find(
        {"case_id": case_id}
    ).sort("uploaded_at", -1))

    # Get chat history
    chats = list(db[Config.CHAT_COLLECTION].find(
        {"case_id": case_id}
    ).sort("timestamp", 1))

    return render_template(
        "case_detail.html",
        case      = case,
        deadlines = deadlines,
        documents = documents,
        chats     = chats
    )


# ── EDIT CASE ─────────────────────────────────────────────
@cases_bp.route("/<case_id>/edit", methods=["GET", "POST"])
@login_required
def edit_case(case_id):
    db = get_db()

    case = db[Config.CASES_COLLECTION].find_one({
        "_id":       ObjectId(case_id),
        "lawyer_id": session["lawyer_id"]
    })

    if not case:
        flash("Case not found.", "error")
        return redirect(url_for("cases.dashboard"))

    if request.method == "POST":
        updated = {
            "title":        request.form.get("title", "").strip(),
            "client_name":  request.form.get("client_name", "").strip(),
            "client_phone": request.form.get("client_phone", "").strip(),
            "client_email": request.form.get("client_email", "").strip(),
            "case_type":    request.form.get("case_type", "").strip(),
            "court_name":   request.form.get("court_name", "").strip(),
            "description":  request.form.get("description", "").strip(),
            "status":       request.form.get("status", "active"),
            "updated_at":   datetime.utcnow()
        }

        db[Config.CASES_COLLECTION].update_one(
            {"_id": ObjectId(case_id)},
            {"$set": updated}
        )

        flash("Case updated successfully!", "success")
        return redirect(url_for("cases.case_detail", case_id=case_id))

    case["_id"] = str(case["_id"])
    return render_template("edit_case.html", case=case)


# ── ARCHIVE CASE ──────────────────────────────────────────
@cases_bp.route("/<case_id>/archive", methods=["POST"])
@login_required
def archive_case(case_id):
    db = get_db()
    db[Config.CASES_COLLECTION].update_one(
        {
            "_id":       ObjectId(case_id),
            "lawyer_id": session["lawyer_id"]
        },
        {"$set": {"status": "archived", "updated_at": datetime.utcnow()}}
    )
    flash("Case archived.", "info")
    return redirect(url_for("cases.dashboard"))


# ── DELETE CASE ───────────────────────────────────────────
@cases_bp.route("/<case_id>/delete", methods=["POST"])
@login_required
def delete_case(case_id):
    db = get_db()

    # Delete case + all related data
    db[Config.CASES_COLLECTION].delete_one({
        "_id":       ObjectId(case_id),
        "lawyer_id": session["lawyer_id"]
    })
    db[Config.DEADLINES_COLLECTION].delete_many({"case_id": case_id})
    db[Config.DOCUMENTS_COLLECTION].delete_many({"case_id": case_id})
    db[Config.CHAT_COLLECTION].delete_many({"case_id": case_id})

    flash("Case deleted successfully.", "info")
    return redirect(url_for("cases.dashboard"))


# ── SEARCH CASES (AJAX) ───────────────────────────────────
@cases_bp.route("/search", methods=["GET"])
@login_required
def search_cases():
    query     = request.args.get("q", "").strip()
    db        = get_db()
    lawyer_id = session["lawyer_id"]

    cases = list(db[Config.CASES_COLLECTION].find({
        "lawyer_id": lawyer_id,
        "$or": [
            {"title":       {"$regex": query, "$options": "i"}},
            {"client_name": {"$regex": query, "$options": "i"}},
            {"case_type":   {"$regex": query, "$options": "i"}}
        ]
    }).limit(10))

    results = []
    for case in cases:
        results.append({
            "id":          str(case["_id"]),
            "title":       case["title"],
            "client_name": case["client_name"],
            "case_type":   case["case_type"],
            "status":      case["status"]
        })

    return jsonify(results)