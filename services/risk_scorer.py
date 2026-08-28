import json
import re
from datetime import datetime
from services.gemini_service import ask_gemini_once


# ── RISK SCORING PROMPT ───────────────────────────────────
RISK_PROMPT = """You are a legal risk assessment expert specializing 
in Indian law and litigation strategy.

Analyze this legal case and return a risk score from 0 to 100.

CASE INFORMATION:
- Title          : {title}
- Case Type      : {case_type}
- Court          : {court_name}
- Status         : {status}
- Description    : {description}
- Documents      : {doc_count} document(s) uploaded
- Open Deadlines : {deadline_count} pending deadline(s)
- Overdue Items  : {overdue_count} overdue item(s)
- Days to Next   : {days_to_next} days until next deadline

SCORING GUIDE:
0-25  : Low Risk    — case is well managed, no immediate concerns
26-50 : Medium Risk — some attention needed
51-75 : High Risk   — urgent action required
76-100: Critical    — immediate intervention needed

Return ONLY a valid JSON object with no extra text:
{{
  "score": <number 0-100>,
  "level": "<Low|Medium|High|Critical>",
  "factors": [
    "<specific risk factor 1>",
    "<specific risk factor 2>",
    "<specific risk factor 3>"
  ],
  "recommendation": "<single most important action to take right now>",
  "breakdown": {{
    "deadline_risk"  : <0-40>,
    "document_risk"  : <0-30>,
    "case_complexity": <0-30>
  }}
}}"""


# ── CLEAN JSON RESPONSE ───────────────────────────────────
def clean_json_response(text):
    """Extract and parse JSON from Gemini response."""
    if not text:
        return None

    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*",     "", text)
    text = text.strip()

    start = text.find("{")
    end   = text.rfind("}") + 1

    if start == -1 or end == 0:
        return None

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        return None


# ── CALCULATE DAYS TO NEXT DEADLINE ──────────────────────
def get_days_to_next_deadline(deadlines):
    """Return number of days until the nearest deadline."""
    if not deadlines:
        return 999

    today = datetime.utcnow()
    min_days = 999

    for dl in deadlines:
        try:
            due  = datetime.strptime(dl["due_date"], "%Y-%m-%d")
            diff = (due - today).days
            if diff < min_days:
                min_days = diff
        except Exception:
            continue

    return min_days


# ── COUNT OVERDUE DEADLINES ───────────────────────────────
def count_overdue(deadlines):
    """Count how many deadlines are past due."""
    today    = datetime.utcnow()
    overdue  = 0

    for dl in deadlines:
        try:
            due = datetime.strptime(dl["due_date"], "%Y-%m-%d")
            if due < today and not dl.get("is_done", False):
                overdue += 1
        except Exception:
            continue

    return overdue


# ── RULE BASED SCORE ──────────────────────────────────────
def rule_based_score(deadlines, documents, days_to_next):
    """
    Calculate a base risk score using simple rules.
    Used as fallback if Gemini fails.

    Returns:
        int — score 0-100
    """
    score = 0

    # Deadline risk (max 40 points)
    overdue = count_overdue(deadlines)
    score  += min(overdue * 15, 30)     # 15 pts per overdue item

    if days_to_next < 0:
        score += 10                      # overdue next deadline
    elif days_to_next <= 1:
        score += 8                       # due tomorrow
    elif days_to_next <= 3:
        score += 5                       # due in 3 days
    elif days_to_next <= 7:
        score += 3                       # due this week

    # Document risk (max 30 points)
    if len(documents) == 0:
        score += 25                      # no documents at all
    elif len(documents) < 2:
        score += 10                      # very few documents

    # Deadline count risk (max 30 points)
    pending = len([d for d in deadlines if not d.get("is_done", False)])
    score  += min(pending * 5, 30)

    return min(score, 100)


# ── GET RISK LEVEL ────────────────────────────────────────
def get_risk_level(score):
    """Return risk level label from score."""
    if score <= 25:
        return "Low"
    elif score <= 50:
        return "Medium"
    elif score <= 75:
        return "High"
    else:
        return "Critical"


# ── MAIN RISK SCORING FUNCTION ────────────────────────────
def calculate_risk_score(case, deadlines, documents):
    """
    Calculate risk score for a case using AI + rule-based fallback.

    Args:
        case      : case dict from MongoDB
        deadlines : list of deadline dicts
        documents : list of document dicts

    Returns:
        dict with keys:
            success        (bool)
            score          (int  0-100)
            level          (str  Low|Medium|High|Critical)
            factors        (list of str)
            recommendation (str)
            breakdown      (dict)
            message        (str)
    """
    # Calculate metrics
    days_to_next   = get_days_to_next_deadline(deadlines)
    overdue_count  = count_overdue(deadlines)
    pending_count  = len([d for d in deadlines
                          if not d.get("is_done", False)])

    # Build prompt
    prompt = RISK_PROMPT.format(
        title          = case.get("title",       "Unknown"),
        case_type      = case.get("case_type",   "Unknown"),
        court_name     = case.get("court_name",  "Unknown"),
        status         = case.get("status",      "active"),
        description    = case.get("description", "No description")[:300],
        doc_count      = len(documents),
        deadline_count = pending_count,
        overdue_count  = overdue_count,
        days_to_next   = days_to_next if days_to_next != 999 else "No deadlines set"
    )

    # Call Gemini
    response = ask_gemini_once(prompt)
    data     = clean_json_response(response) if response else None

    # Use AI result if valid
    if data and "score" in data:
        score = max(0, min(100, int(data["score"])))
        return {
            "success":        True,
            "score":          score,
            "level":          data.get("level",          get_risk_level(score)),
            "factors":        data.get("factors",        []),
            "recommendation": data.get("recommendation", "Review case immediately."),
            "breakdown":      data.get("breakdown",      {}),
            "message":        "Risk score calculated successfully."
        }

    # Fallback to rule-based scoring
    print("⚠️ Gemini unavailable, using rule-based scoring.")
    score = rule_based_score(deadlines, documents, days_to_next)

    factors = []
    if overdue_count > 0:
        factors.append(f"{overdue_count} overdue deadline(s)")
    if len(documents) == 0:
        factors.append("No documents uploaded")
    if days_to_next <= 3:
        factors.append(f"Next deadline in {days_to_next} day(s)")
    if not factors:
        factors.append("Case appears well managed")

    return {
        "success":        True,
        "score":          score,
        "level":          get_risk_level(score),
        "factors":        factors,
        "recommendation": "Review all pending deadlines and upload case documents.",
        "breakdown": {
            "deadline_risk":   min(overdue_count * 15, 40),
            "document_risk":   25 if len(documents) == 0 else 0,
            "case_complexity": 20
        },
        "message": "Risk score calculated (rule-based fallback)."
    } 
