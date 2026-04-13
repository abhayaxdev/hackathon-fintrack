import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Fallback narrative — returned whenever the LLM call fails or the
# API key is not configured. Must never raise; must always return a string.
# ------------------------------------------------------------------
FALLBACK_NARRATIVE = (
    "Great job tracking your expenses! Here are a few universal tips for the month ahead: "
    "First, review your discretionary spending — eating out, entertainment, and subscriptions "
    "often have the most room to trim without affecting your quality of life. "
    "Second, aim to set aside at least 10% of your income into savings before budgeting the rest. "
    "Third, if any category spiked unexpectedly this month, identify whether it was a one-off "
    "expense or the start of a new pattern — that distinction changes how you should respond."
)


def _build_prompt(packet: dict) -> str:
    """
    Converts the summary packet into a readable prompt string.
    We deliberately avoid sending raw JSON to the LLM — prose context
    produces more natural narrative output than key-value dumps.
    """
    subject  = packet['subject_month']
    baseline = packet['baseline_month']
    total_this = packet['total_this_month']
    total_last = packet['total_last_month']
    total_var  = packet['total_variance_pct']

    lines = [
        f"Monthly spending comparison for a user based in Nepal.",
        f"",
        f"Reference month: {subject}",
        f"Previous month:  {baseline}",
        f"",
        f"Overall: spent {total_this:,.2f} this month vs {total_last:,.2f} last month "
        + (f"({total_var:+.1f}% change)." if total_var is not None else "(no prior data for comparison)."),
        f"",
        f"Breakdown by category:",
    ]

    for row in packet['categories']:
        cat  = row['category']
        this = row['this_month']
        last = row['last_month']
        var  = row['variance_pct']

        if var is None:
            lines.append(f"  - {cat}: {this:,.2f} (new category, no data last month)")
        elif last == 0:
            lines.append(f"  - {cat}: {this:,.2f} (new category)")
        elif this == 0:
            lines.append(f"  - {cat}: nothing spent this month vs {last:,.2f} last month ({var:+.1f}%)")
        else:
            lines.append(f"  - {cat}: {this:,.2f} this month vs {last:,.2f} last month ({var:+.1f}%)")

    return "\n".join(lines)


SYSTEM_INSTRUCTION = (
    "You are a supportive, professional financial coach for a user based in Nepal. "
    "You have been given a structured monthly spending comparison. "
    "Do NOT list or repeat the raw numbers back to the user. "
    "Instead, interpret what the numbers mean in plain, conversational language — "
    "for example, instead of saying 'Food is +40%', say something like "
    "'Your grocery spending climbed notably compared to last month'. "
    "Provide exactly 2 to 3 short, actionable suggestions for the upcoming month. "
    "Be encouraging but honest. Keep the entire response under 120 words."
)


def _call_gemini(prompt_text: str) -> str:
    """
    Send the prompt to Gemini and return the narrative string.
    Raises on any error so the caller can fall back gracefully.
    """
    import google.generativeai as genai  # lazy import — only fails if not installed

    cfg = settings.INSIGHT_ENGINE
    genai.configure(api_key=cfg['api_key'])

    model = genai.GenerativeModel(
        model_name=cfg.get('model', 'gemini-1.5-flash'),
        system_instruction=SYSTEM_INSTRUCTION,
    )
    response = model.generate_content(prompt_text)
    return response.text.strip()


class LLMConnector:
    """
    Wraps the Gemini API call. Always returns a string — either the
    LLM-generated narrative or the hardcoded fallback.
    """

    def generate(self, packet: dict) -> tuple[str, bool]:
        """
        Returns (narrative_string, used_fallback).
        used_fallback=True means the LLM was unavailable and the generic tip was returned.
        """
        cfg = getattr(settings, 'INSIGHT_ENGINE', {})
        api_key = cfg.get('api_key', '')

        if not api_key:
            logger.warning(
                "LLMConnector: INSIGHT_ENGINE api_key is not configured. "
                "Returning fallback narrative."
            )
            return FALLBACK_NARRATIVE, True

        if not packet.get('categories'):
            logger.info(
                "LLMConnector: empty summary packet (no transaction data). "
                "Returning fallback narrative."
            )
            return FALLBACK_NARRATIVE, True

        prompt_text = _build_prompt(packet)

        try:
            narrative = _call_gemini(prompt_text)
            logger.info("LLMConnector: Gemini response received successfully.")
            return narrative, False

        except Exception as exc:
            logger.warning(
                f"LLMConnector: Gemini API call failed — {type(exc).__name__}: {exc}. "
                f"Returning fallback narrative."
            )
            return FALLBACK_NARRATIVE, True
