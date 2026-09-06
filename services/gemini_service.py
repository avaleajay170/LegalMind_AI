from google import genai
from config import Config

# ── CONFIGURE GEMINI CLIENT ───────────────────────────────
client = genai.Client(api_key=Config.GEMINI_API_KEY)

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
  1. RELEVANT SECTIONS — list exact act + section numbers
  2. LEGAL POSITION    — 2-3 sentence summary
  3. KEY PRECEDENTS    — notable cases if applicable
  4. STRATEGIC INSIGHT — practical implications
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
}}"""
}


# ── MAIN GEMINI FUNCTION ──────────────────────────────────
def ask_gemini(message, case_context="", history=[], mode="chat"):
    """
    Send a message to Gemini and get a response.

    Args:
        message      : The user's message or query
        case_context : Case details or retrieved legal context
        history      : List of previous messages [{role, content}]
        mode         : chat | research | draft | risk

    Returns:
        str — Gemini's response
    """
    try:
        # Build system prompt with context
        system_prompt = PROMPTS.get(mode, PROMPTS["chat"]).format(
            case_context=case_context
        )

        # Build full message
        full_message = f"{system_prompt}\n\nUser Query: {message}"

        # Build contents with history
        contents = []
        for h in history:
            role = "user" if h["role"] == "user" else "model"
            contents.append(
                genai.types.Content(
                    role  = role,
                    parts = [genai.types.Part(text=h["content"])]
                )
            )

        # Add current message
        contents.append(
            genai.types.Content(
                role  = "user",
                parts = [genai.types.Part(text=full_message)]
            )
        )

        response = client.models.generate_content(
            model    = Config.GEMINI_MODEL,
            contents = contents
        )

        return response.text

    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return f"AI service temporarily unavailable. Please try again."


# ── SIMPLE ONE-SHOT GEMINI CALL ───────────────────────────
def ask_gemini_once(prompt):
    """
    Simple single prompt → response.
    Used for section suggester and risk scorer.

    Args:
        prompt : Full prompt string

    Returns:
        str — Gemini's response
    """
    try:
        response = client.models.generate_content(
            model    = Config.GEMINI_MODEL,
            contents = prompt
        )
        return response.text

    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return None