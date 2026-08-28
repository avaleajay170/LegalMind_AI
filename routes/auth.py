from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from bson import ObjectId

from models.database import get_db
from config import Config
from services.advocate_registry import (
    verify_advocate,
    check_duplicate_enrollment,
    get_state_name
)

auth_bp = Blueprint("auth", __name__)


# ── LOGIN REQUIRED DECORATOR ─────────────────────────────
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "lawyer_id" not in session:
            flash("Please login to access this page.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ── LOGIN ────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Already logged in
    if "lawyer_id" in session:
        return redirect(url_for("cases.dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        # Basic validation
        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template("login.html")

        # Find user in MongoDB
        db   = get_db()
        user = db[Config.USERS_COLLECTION].find_one({"email": email})

        if not user:
            flash("No account found with this email.", "error")
            return render_template("login.html")

        # Check password
        if not check_password_hash(user["password_hash"], password):
            flash("Incorrect password. Please try again.", "error")
            return render_template("login.html")

        # Set session
        session["lawyer_id"]      = str(user["_id"])
        session["lawyer_name"]    = user["full_name"]
        session["enrollment_no"]  = user["enrollment_no"]
        session["state"]          = user["state"]
        session["bar_council"]    = user.get("bar_council", "")
        session["role"]           = user.get("role", "lawyer")

        flash(f"Welcome back, Advocate {user['full_name']}!", "success")
        return redirect(url_for("cases.dashboard"))

    return render_template("login.html")


# ── REGISTER — STEP 1: VERIFY ENROLLMENT ─────────────────
@auth_bp.route("/verify-enrollment", methods=["POST"])
def verify_enrollment():
    """
    AJAX endpoint — verifies Bar Council enrollment.
    Called from register page before showing account form.
    """
    data          = request.get_json()
    full_name     = data.get("full_name", "").strip()
    enrollment_no = data.get("enrollment_no", "").strip().upper()
    state         = data.get("state", "").strip().upper()

    if not full_name or not enrollment_no or not state:
        return jsonify({
            "success": False,
            "message": "Please fill in all fields."
        })

    # Check if already registered
    if check_duplicate_enrollment(enrollment_no):
        return jsonify({
            "success": False,
            "message": "An account with this enrollment number already exists. Please login."
        })

    # Verify against registry
    result = verify_advocate(full_name, enrollment_no, state)
    return jsonify(result)


# ── REGISTER — STEP 2: CREATE ACCOUNT ────────────────────
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "lawyer_id" in session:
        return redirect(url_for("cases.dashboard"))

    if request.method == "POST":
        # Get form data
        full_name      = request.form.get("full_name", "").strip()
        enrollment_no  = request.form.get("enrollment_no", "").strip().upper()
        state          = request.form.get("state", "").strip().upper()
        email          = request.form.get("email", "").strip().lower()
        password       = request.form.get("password", "").strip()
        confirm_pw     = request.form.get("confirm_password", "").strip()
        specialization = request.form.get("specialization", "").strip()

        # ── VALIDATIONS ──────────────────────────────────
        if not all([full_name, enrollment_no, state, email, password]):
            flash("All fields are required.", "error")
            return render_template("register.html")

        if password != confirm_pw:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html")

        # Check duplicate email
        db = get_db()
        if db[Config.USERS_COLLECTION].find_one({"email": email}):
            flash("An account with this email already exists.", "error")
            return render_template("register.html")

        # Check duplicate enrollment
        if check_duplicate_enrollment(enrollment_no):
            flash("This enrollment number is already registered.", "error")
            return render_template("register.html")

        # Verify Bar Council enrollment
        result = verify_advocate(full_name, enrollment_no, state)
        if not result["success"]:
            flash(result["message"], "error")
            return render_template("register.html")

        # ── CREATE USER IN MONGODB ───────────────────────
        advocate   = result["advocate"]
        new_user   = {
            "full_name":      full_name,
            "email":          email,
            "password_hash":  generate_password_hash(password),
            "enrollment_no":  enrollment_no,
            "state":          state,
            "bar_council":    advocate.get("bar_council", ""),
            "specialization": specialization or advocate.get("specialization", ""),
            "role":           "lawyer",
            "is_verified":    True,
            "created_at":     datetime.utcnow()
        }

        inserted = db[Config.USERS_COLLECTION].insert_one(new_user)

        # Auto login after register
        session["lawyer_id"]     = str(inserted.inserted_id)
        session["lawyer_name"]   = full_name
        session["enrollment_no"] = enrollment_no
        session["state"]         = state
        session["bar_council"]   = advocate.get("bar_council", "")
        session["role"]          = "lawyer"

        flash(f"Account created! Welcome to LegalMind AI, Advocate {full_name}.", "success")
        return redirect(url_for("cases.dashboard"))

    return render_template("register.html")


# ── LOGOUT ───────────────────────────────────────────────
@auth_bp.route("/logout")
def logout():
    lawyer_name = session.get("lawyer_name", "")
    session.clear()
    flash(f"Goodbye, {lawyer_name}. You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ── PROFILE ──────────────────────────────────────────────
@auth_bp.route("/profile")
@login_required
def profile():
    db   = get_db()
    user = db[Config.USERS_COLLECTION].find_one(
        {"_id": ObjectId(session["lawyer_id"])}
    )
    return render_template("profile.html", user=user) 
