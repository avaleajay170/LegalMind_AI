import time
from google import genai
from config import Config

# ── CLIENT ────────────────────────────────────────────────
client = genai.Client(api_key=Config.GEMINI_API_KEY)

# ── FALLBACK MODEL CHAIN ──────────────────────────────────
# Tried in order — first available and working model is used
MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
]

# ── SYSTEM PROMPTS ────────────────────────────────────────
PROMPTS = {

    "chat": """You are LegalMind AI, an expert legal assistant
specializing in Indian law. You are assisting a verified advocate.

CASE CONTEXT:
{case_context}

INSTRUCTIONS:
- Answer questions using the case context provided
- Cite relevant IPC, CrPC, CPC sections where applicable
- Flag any risks or missing documents clearly
- Be concise, professional and precise
- Always respond in English
- Never make up facts — if unsure, say so""",

    "research": """You are a legal research assistant specializing
in Indian law including IPC, CrPC, CPC, IBC, IT Act, POCSO and more.

RETRIEVED LEGAL CONTEXT:
{case_context}

INSTRUCTIONS:
- Respond with clearly structured legal research
- Always cite specific Act names and section numbers
- Format your response as:
  1. RELEVANT SECTIONS  — list exact act + section numbers
  2. LEGAL POSITION     — 2-3 sentence summary
  3. KEY PRECEDENTS     — notable cases if applicable
  4. STRATEGIC INSIGHT  — practical implications
- Be precise and cite sources""",

    "draft": """You are an expert legal document drafter for
Indian courts and legal proceedings.

CASE DETAILS:
{case_context}

INSTRUCTIONS:
- Draft a complete, formal legal document
- Use standard Indian court formatting
- Include all mandatory sections for this document type
- Use proper legal language and citations
- Return only the document text, ready to use
- Include placeholders like [DATE], [COURT NAME] where needed""",

    "risk": """You are a legal risk assessment expert specializing
in Indian law and litigation.

CASE DETAILS:
{case_context}

INSTRUCTIONS:
- Analyze the case and return a JSON risk assessment
- Score from 0 (very low risk) to 100 (critical risk)
- Return ONLY valid JSON, no extra text
- Format:
{{
  "score": <number 0-100>,
  "level": "<Low|Medium|High|Critical>",
  "factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "recommendation": "<one clear action to take right now>",
  "breakdown": {{
    "deadline_risk"  : <0-40>,
    "document_risk"  : <0-30>,
    "case_complexity": <0-30>
  }}
}}"
"""
}


# ── ERROR CLASSIFIER ──────────────────────────────────────
def _is_retryable(error_text):
    """503 / 429 = overloaded, worth retrying."""
    return any(code in error_text for code in [
        "503", "UNAVAILABLE",
        "429", "RESOURCE_EXHAUSTED",
    ])


def _is_model_gone(error_text):
    """404 = model removed, skip to next immediately."""
    return any(code in error_text for code in [
        "404", "NOT_FOUND", "no longer available",
    ])


# ── CORE GENERATION WITH FALLBACK ─────────────────────────
def _generate(contents, retries=3):
    """
    Try each model in MODELS list.
    For 503/429 errors  → retry with exponential backoff.
    For 404 errors      → skip to next model immediately.
    For other errors    → skip to next model.

    Args:
        contents : str or list[genai.types.Content]
        retries  : attempts per model for retryable errors

    Returns:
        str — response text, or None if everything failed
    """
    last_error = None

    for model in MODELS:
        for attempt in range(1, retries + 1):
            try:
                print(f"🤖 Trying {model} "
                      f"(attempt {attempt}/{retries})")

                response = client.models.generate_content(
                    model    = model,
                    contents = contents
                )

                if response and response.text:
                    print(f"✅ Success with {model}")
                    return response.text

                print("⚠️ Empty response — trying next model")
                break

            except Exception as e:
                last_error   = e
                error_text   = str(e)
                short_error  = error_text[:100]

                print(f"❌ {model} attempt {attempt}: {short_error}")

                if _is_model_gone(error_text):
                    print(f"⏭ {model} unavailable — skipping")
                    break

                if _is_retryable(error_text):
                    if attempt < retries:
                        wait = 2 ** (attempt - 1)   # 1s, 2s, 4s
                        print(f"⏳ Retrying in {wait}s...")
                        time.sleep(wait)
                        continue
                    else:
                        print(f"⏭ Max retries reached — "
                              f"trying next model")
                        break

                # Unknown error — skip model
                break

    print(f"❌ All models failed. Last error: {last_error}")
    return None


# ── PUBLIC: CHAT / RESEARCH / DRAFT / RISK ────────────────
def ask_gemini(message, case_context="",
               history=None, mode="chat"):
    """
    Full conversation call with system prompt + history.

    Args:
        message      : user's question or request
        case_context : case data or retrieved legal text
        history      : list of {role, content} dicts
        mode         : chat | research | draft | risk

    Returns:
        str — AI response
    """
    if history is None:
        history = []

    try:
        system_prompt = PROMPTS.get(
            mode, PROMPTS["chat"]
        ).format(case_context=case_context)

        full_message = f"{system_prompt}\n\nUser Query: {message}"

        # Build content list with history
        contents = []
        for h in history:
            role = "user" if h.get("role") == "user" else "model"
            contents.append(
                genai.types.Content(
                    role  = role,
                    parts = [genai.types.Part(
                        text = h.get("content", "")
                    )]
                )
            )

        # Add current message
        contents.append(
            genai.types.Content(
                role  = "user",
                parts = [genai.types.Part(text=full_message)]
            )
        )

        result = _generate(contents)
        return result or (
            "AI service is temporarily unavailable due to high "
            "demand. Please try again in a moment."
        )

    except Exception as e:
        print(f"❌ ask_gemini error: {e}")
        return "AI service temporarily unavailable. Please try again."


# ── PUBLIC: ONE-SHOT CALL ─────────────────────────────────
def ask_gemini_once(prompt):
    """
    Simple prompt → response, no history.
    Used by section suggester, doc generator, risk scorer.

    Args:
        prompt : full prompt string

    Returns:
        str or None
    """
    try:
        return _generate(prompt)
    except Exception as e:
        print(f"❌ ask_gemini_once error: {e}")
        return None