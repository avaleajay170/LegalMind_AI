import json
import re
from services.gemini_service import ask_gemini_once


# ── SECTION SUGGESTER PROMPT ──────────────────────────────
SECTION_PROMPT = """You are an expert in Indian criminal and civil law.
Analyze the following incident description and identify all applicable 
legal sections under Indian law.

INCIDENT DESCRIPTION:
{incident_text}

You MUST respond with ONLY a valid JSON object — no extra text, 
no markdown, no explanation before or after.

Return this exact JSON structure:
{{
  "primary_sections": [
    {{
      "act": "IPC",
      "section": "302",
      "title": "Murder",
      "punishment": "Death or life imprisonment",
      "reason": "The incident involves intentional killing"
    }}
  ],
  "supporting_sections": [
    {{
      "act": "IPC",
      "section": "120-B",
      "title": "Criminal Conspiracy",
      "punishment": "Same as main offence",
      "reason": "Multiple people were involved in planning"
    }}
  ],
  "bailable": false,
  "cognizable": true,
  "court": "Sessions Court",
  "fir_type": "Zero FIR applicable",
  "next_steps": [
    "File FIR under Section 302 immediately",
    "Request forensic report under Section 293 CrPC",
    "Apply for police custody remand"
  ],
  "summary": "This is a case of murder with criminal conspiracy."
}}

IMPORTANT RULES:
- primary_sections   : sections that MUST apply to this incident
- supporting_sections: sections that MAY apply depending on evidence
- bailable           : true if offence is bailable, false if non-bailable
- cognizable         : true if police can arrest without warrant
- court              : which court has jurisdiction
- fir_type           : type of FIR to file
- next_steps         : 3-5 immediate actions for the advocate
- summary            : one sentence describing the legal nature
- Cover IPC, CrPC, IT Act, POCSO, NDPS, IBC as applicable
- Return ONLY the JSON object, nothing else"""


# ── CLEAN JSON RESPONSE ───────────────────────────────────
def clean_json_response(text):
    """
    Clean Gemini response to extract valid JSON.
    Handles cases where Gemini adds markdown or extra text.
    """
    if not text:
        return None

    # Remove markdown code blocks
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*",     "", text)
    text = text.strip()

    # Find JSON object in response
    start = text.find("{")
    end   = text.rfind("}") + 1

    if start == -1 or end == 0:
        return None

    json_str = text[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print(f"Raw response: {text[:200]}")
        return None


# ── MAIN SUGGEST FUNCTION ─────────────────────────────────
def suggest_sections(incident_text):
    """
    Analyze incident and suggest applicable IPC/CrPC sections.

    Args:
        incident_text : plain language description of the incident

    Returns:
        dict with keys:
            success (bool)
            data    (dict) — structured section suggestions
            message (str)  — error message if failed
    """
    if not incident_text or len(incident_text.strip()) < 20:
        return {
            "success": False,
            "data":    None,
            "message": "Please provide a detailed incident description."
        }

    # Build prompt
    prompt = SECTION_PROMPT.format(
        incident_text=incident_text.strip()
    )

    # Call Gemini
    response = ask_gemini_once(prompt)

    if not response:
        return {
            "success": False,
            "data":    None,
            "message": "AI service unavailable. Please try again."
        }

    # Parse JSON response
    data = clean_json_response(response)

    if not data:
        return {
            "success": False,
            "data":    None,
            "message": "Could not parse AI response. Please try again."
        }

    # Validate required fields
    required = [
        "primary_sections",
        "supporting_sections",
        "bailable",
        "cognizable",
        "court",
        "next_steps"
    ]

    for field in required:
        if field not in data:
            data[field] = [] if "sections" in field or \
                          "steps"    in field else "Unknown"

    return {
        "success": True,
        "data":    data,
        "message": "Sections identified successfully."
    }


# ── FORMAT OUTPUT FOR DISPLAY ─────────────────────────────
def format_sections_display(data):
    """
    Format section suggestions for HTML display.

    Args:
        data : parsed JSON from suggest_sections()

    Returns:
        dict — formatted display data
    """
    if not data:
        return {}

    # Bailable flag
    bailable_text  = "Bailable"     if data.get("bailable")   else "Non-Bailable"
    cognizable_text= "Cognizable"   if data.get("cognizable")  else "Non-Cognizable"

    # Color codes
    bailable_color  = "green" if data.get("bailable")  else "red"
    cognizable_color= "blue"  if data.get("cognizable") else "amber"

    return {
        "primary_sections":    data.get("primary_sections",    []),
        "supporting_sections": data.get("supporting_sections", []),
        "flags": {
            "bailable":  {
                "text":  bailable_text,
                "color": bailable_color
            },
            "cognizable": {
                "text":  cognizable_text,
                "color": cognizable_color
            }
        },
        "court":      data.get("court",    "Unknown"),
        "fir_type":   data.get("fir_type", "Regular FIR"),
        "next_steps": data.get("next_steps", []),
        "summary":    data.get("summary",   "")
    } 
