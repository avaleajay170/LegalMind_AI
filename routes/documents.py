from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash,
    jsonify, send_file, current_app
)
from datetime import datetime
from bson import ObjectId
import os
import uuid

from models.database import get_db
from config import Config
from routes.auth import login_required
from services.pdf_service import extract_text_from_pdf

docs_bp = Blueprint("documents", __name__)


# ── HELPER: ALLOWED FILE ──────────────────────────────────
def allowed_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS
    )


def secure_unique_filename(filename):
    """Generate a unique filename to avoid overwrites."""
    ext      = filename.rsplit(".", 1)[1].lower() if "." in filename else "pdf"
    unique   = str(uuid.uuid4())[:8]
    safe     = filename.rsplit(".", 1)[0].replace(" ", "_")[:40]
    return f"{safe}_{unique}.{ext}"


# ── UPLOAD DOCUMENT ───────────────────────────────────────
@docs_bp.route("/upload", methods=["POST"])
@login_required
def upload_document():
    case_id  = request.form.get("case_id", "").strip()
    doc_type = request.form.get("doc_type", "uploaded").strip()

    if not case_id:
        flash("Case ID is required.", "error")
        return redirect(request.referrer or url_for("cases.dashboard"))

    if "file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("cases.case_detail", case_id=case_id))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("cases.case_detail", case_id=case_id))

    if not allowed_file(file.filename):
        flash("Invalid file type. Allowed: PDF, DOC, DOCX, TXT.", "error")
        return redirect(url_for("cases.case_detail", case_id=case_id))

    # ── SAVE FILE ─────────────────────────────────────────
    filename    = secure_unique_filename(file.filename)
    upload_dir  = os.path.join(
        current_app.config["UPLOAD_FOLDER"], case_id
    )
    os.makedirs(upload_dir, exist_ok=True)
    filepath    = os.path.join(upload_dir, filename)
    file.save(filepath)

    # ── EXTRACT TEXT ──────────────────────────────────────
    extracted_text = ""
    if filename.endswith(".pdf"):
        extracted_text = extract_text_from_pdf(filepath)

    # ── SAVE TO MONGODB ───────────────────────────────────
    db          = get_db()
    file_size   = os.path.getsize(filepath)

    new_doc = {
        "case_id":        case_id,
        "lawyer_id":      session["lawyer_id"],
        "filename":       filename,
        "original_name":  file.filename,
        "filepath":       filepath,
        "doc_type":       doc_type,
        "extracted_text": extracted_text,
        "file_size":      file_size,
        "uploaded_at":    datetime.utcnow()
    }

    db[Config.DOCUMENTS_COLLECTION].insert_one(new_doc)
    flash(f"Document '{file.filename}' uploaded and processed!", "success")
    return redirect(url_for("cases.case_detail", case_id=case_id))


# ── LIST DOCUMENTS FOR A CASE ─────────────────────────────
@docs_bp.route("/case/<case_id>", methods=["GET"])
@login_required
def list_documents(case_id):
    db   = get_db()
    docs = list(db[Config.DOCUMENTS_COLLECTION].find(
        {"case_id": case_id}
    ).sort("uploaded_at", -1))

    for doc in docs:
        doc["_id"] = str(doc["_id"])
        # Convert bytes to KB
        doc["file_size_kb"] = round(
            doc.get("file_size", 0) / 1024, 1
        )

    return jsonify(docs)


# ── DOWNLOAD DOCUMENT ─────────────────────────────────────
@docs_bp.route("/download/<doc_id>", methods=["GET"])
@login_required
def download_document(doc_id):
    db  = get_db()
    doc = db[Config.DOCUMENTS_COLLECTION].find_one(
        {"_id": ObjectId(doc_id)}
    )

    if not doc:
        flash("Document not found.", "error")
        return redirect(url_for("cases.dashboard"))

    if not os.path.exists(doc["filepath"]):
        flash("File not found on server.", "error")
        return redirect(url_for("cases.dashboard"))

    return send_file(
        doc["filepath"],
        as_attachment=True,
        download_name=doc.get("original_name", doc["filename"])
    )


# ── DELETE DOCUMENT ───────────────────────────────────────
@docs_bp.route("/delete/<doc_id>", methods=["POST"])
@login_required
def delete_document(doc_id):
    db  = get_db()
    doc = db[Config.DOCUMENTS_COLLECTION].find_one(
        {"_id": ObjectId(doc_id)}
    )

    if not doc:
        flash("Document not found.", "error")
        return redirect(request.referrer or url_for("cases.dashboard"))

    # Delete physical file
    if os.path.exists(doc["filepath"]):
        os.remove(doc["filepath"])

    # Delete from MongoDB
    db[Config.DOCUMENTS_COLLECTION].delete_one(
        {"_id": ObjectId(doc_id)}
    )

    flash("Document deleted.", "info")
    return redirect(
        url_for("cases.case_detail", case_id=doc["case_id"])
    )


# ── VIEW EXTRACTED TEXT ───────────────────────────────────
@docs_bp.route("/extracted-text/<doc_id>", methods=["GET"])
@login_required
def extracted_text(doc_id):
    db  = get_db()
    doc = db[Config.DOCUMENTS_COLLECTION].find_one(
        {"_id": ObjectId(doc_id)}
    )

    if not doc:
        return jsonify({
            "success": False,
            "message": "Document not found."
        })

    return jsonify({
        "success":        True,
        "filename":       doc.get("original_name", doc["filename"]),
        "extracted_text": doc.get("extracted_text", "No text extracted.")
    })


# ── DOWNLOAD GENERATED DOCUMENT ───────────────────────────
@docs_bp.route("/generated/<filename>", methods=["GET"])
@login_required
def download_generated(filename):
    filepath = os.path.join(
        current_app.config["GENERATED_FOLDER"], filename
    )

    if not os.path.exists(filepath):
        flash("Generated file not found.", "error")
        return redirect(url_for("cases.dashboard"))

    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename
    ) 
