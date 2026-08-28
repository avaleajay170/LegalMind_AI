from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash, jsonify
)
from datetime import datetime, timedelta
from bson import ObjectId

from models.database import get_db
from config import Config
from routes.auth import login_required

deadlines_bp = Blueprint("deadlines", __name__)


# ── HELPER: CALCULATE URGENCY ─────────────────────────────
def calculate_urgency(due_date_str):
    """Return urgency color based on days remaining."""
    try:
        due  = datetime.strptime(due_date_str, "%Y-%m-%d")
        diff = (due - datetime.utcnow()).days
        if diff < 0:
            return "red"       # overdue
        elif diff <= 3:
            return "amber"     # due soon
        else:
            return "green"     # safe
    except Exception:
        return "green"


# ── ALL DEADLINES — CALENDAR VIEW ─────────────────────────
@deadlines_bp.route("/")
@login_required
def all_deadlines():
    db        = get_db()
    lawyer_id = session["lawyer_id"]

    # Get all cases for this lawyer
    cases = list(db[Config.CASES_COLLECTION].find(
        {"lawyer_id": lawyer_id, "status": {"$ne": "archived"}}
    ))

    case_ids  = [str(c["_id"]) for c in cases]
    case_map  = {str(c["_id"]): c["title"] for c in cases}

    # Get all deadlines across all cases
    deadlines = list(db[Config.DEADLINES_COLLECTION].find(
        {"case_id": {"$in": case_ids}}
    ).sort("due_date", 1))

    # Attach case title + urgency to each deadline
    for dl in deadlines:
        dl["case_title"] = case_map.get(dl["case_id"], "Unknown Case")
        dl["urgency"]    = calculate_urgency(dl["due_date"])
        dl["_id"]        = str(dl["_id"])

    # Split into categories
    overdue = [d for d in deadlines if d["urgency"] == "red"   and not d["is_done"]]
    soon    = [d for d in deadlines if d["urgency"] == "amber" and not d["is_done"]]
    safe    = [d for d in deadlines if d["urgency"] == "green" and not d["is_done"]]
    done    = [d for d in deadlines if d["is_done"]]

    return render_template(
        "deadlines.html",
        overdue  = overdue,
        soon     = soon,
        safe     = safe,
        done     = done,
        all_deadlines = deadlines,
        cases    = cases
    )


# ── ADD DEADLINE ──────────────────────────────────────────
@deadlines_bp.route("/add", methods=["POST"])
@login_required
def add_deadline():
    case_id       = request.form.get("case_id", "").strip()
    title         = request.form.get("title", "").strip()
    due_date      = request.form.get("due_date", "").strip()
    deadline_type = request.form.get("deadline_type", "hearing").strip()
    notes         = request.form.get("notes", "").strip()

    if not case_id or not title or not due_date:
        flash("Case, title and due date are required.", "error")
        return redirect(request.referrer or url_for("deadlines.all_deadlines"))

    db      = get_db()
    urgency = calculate_urgency(due_date)

    new_deadline = {
        "case_id":       case_id,
        "lawyer_id":     session["lawyer_id"],
        "title":         title,
        "due_date":      due_date,
        "deadline_type": deadline_type,
        "urgency":       urgency,
        "is_done":       False,
        "notes":         notes,
        "created_at":    datetime.utcnow()
    }

    db[Config.DEADLINES_COLLECTION].insert_one(new_deadline)
    flash(f"Deadline '{title}' added successfully!", "success")

    # Redirect back to case detail if came from there
    referer = request.referrer or ""
    if "cases" in referer:
        return redirect(url_for("cases.case_detail", case_id=case_id))

    return redirect(url_for("deadlines.all_deadlines"))


# ── MARK DONE ─────────────────────────────────────────────
@deadlines_bp.route("/<deadline_id>/done", methods=["POST"])
@login_required
def mark_done(deadline_id):
    db = get_db()

    deadline = db[Config.DEADLINES_COLLECTION].find_one(
        {"_id": ObjectId(deadline_id)}
    )

    if not deadline:
        return jsonify({"success": False, "message": "Deadline not found."})

    db[Config.DEADLINES_COLLECTION].update_one(
        {"_id": ObjectId(deadline_id)},
        {"$set": {"is_done": True, "completed_at": datetime.utcnow()}}
    )

    return jsonify({"success": True, "message": "Deadline marked as done."})


# ── EDIT 
