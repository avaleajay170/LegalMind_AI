import json
import re
import os
from config import Config


def load_registry():
    """Load advocate registry from JSON file."""
    try:
        with open(Config.REGISTRY_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Registry file not found at {Config.REGISTRY_PATH}")
        return []
    except json.JSONDecodeError:
        print("❌ Registry file is corrupted.")
        return []


def validate_enrollment_format(enrollment_no):
    """
    Validate enrollment number format.
    Valid formats: MH/1234/2020, D/5678/2019, KAR/2341/2021
    Pattern: STATE_CODE / NUMBER / YEAR
    """
    pattern = r"^[A-Z]{1,4}\/\d{3,6}\/\d{4}$"
    return bool(re.match(pattern, enrollment_no.strip().upper()))


def verify_advocate(full_name, enrollment_no, state):
    """
    Verify advocate against the local Bar Council registry.

    Returns:
        dict with keys:
            success  (bool)
            message  (str)
            advocate (dict or None)
    """
    # ── STEP 1: Format validation ────────────────────────
    enrollment_no = enrollment_no.strip().upper()

    if not validate_enrollment_format(enrollment_no):
        return {
            "success": False,
            "message": "Invalid enrollment number format. Use STATE/NUMBER/YEAR (e.g. MH/1234/2020)",
            "advocate": None
        }

    # ── STEP 2: Load registry ────────────────────────────
    registry = load_registry()

    if not registry:
        return {
            "success": False,
            "message": "Registry unavailable. Please contact support.",
            "advocate": None
        }

    # ── STEP 3: Match against registry ──────────────────
    for advocate in registry:
        name_match       = advocate["full_name"].lower().strip() == full_name.lower().strip()
        enrollment_match = advocate["enrollment_no"].upper()     == enrollment_no
        state_match      = advocate["state"].upper()             == state.upper()

        if name_match and enrollment_match and state_match:

            # Check if advocate is active
            if not advocate.get("is_active", True):
                return {
                    "success": False,
                    "message": "Your Bar Council enrollment is marked inactive. Please contact your Bar Council.",
                    "advocate": None
                }

            return {
                "success": True,
                "message": f"Verified — {advocate['full_name']} found in {advocate['bar_council']}",
                "advocate": advocate
            }

    # ── STEP 4: Not found ────────────────────────────────
    return {
        "success": False,
        "message": "Advocate not found. Please check your name, enrollment number, and state match Bar Council records exactly.",
        "advocate": None
    }


def check_duplicate_enrollment(enrollment_no):
    """
    Check if enrollment number is already registered in MongoDB.
    Returns True if already exists, False if available.
    """
    from models.database import get_db
    from config import Config

    db = get_db()
    existing = db[Config.USERS_COLLECTION].find_one(
        {"enrollment_no": enrollment_no.strip().upper()}
    )
    return existing is not None


def get_state_name(state_code):
    """Return full state name from state code."""
    states = {
        "MH":  "Maharashtra",
        "D":   "Delhi",
        "KAR": "Karnataka",
        "TN":  "Tamil Nadu",
        "UP":  "Uttar Pradesh",
        "GUJ": "Gujarat",
        "WB":  "West Bengal",
        "RAJ": "Rajasthan",
        "TS":  "Telangana",
        "KL":  "Kerala",
        "MP":  "Madhya Pradesh",
        "PB":  "Punjab",
        "HR":  "Haryana",
        "OR":  "Odisha",
        "AP":  "Andhra Pradesh",
        "BR":  "Bihar",
        "JH":  "Jharkhand",
        "CG":  "Chhattisgarh",
        "UK":  "Uttarakhand",
        "HP":  "Himachal Pradesh",
        "GA":  "Goa",
        "MN":  "Manipur",
        "AS":  "Assam",
    }
    return states.get(state_code.upper(), state_code)