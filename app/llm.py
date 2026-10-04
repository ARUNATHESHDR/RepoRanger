"""LLM factory — prefers Google Gemini (fast, free tier); falls back to Groq."""
from langchain_core.language_models import BaseChatModel

from .config import settings


def get_llm(temperature: float = 0.0) -> BaseChatModel:
    """Return the best available LLM. Google Gemini Flash is preferred for speed."""
    if settings.google_api_key:
        # Use Google Gemini Flash — fastest option, free on AI Studio
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            temperature=temperature,
            google_api_key=settings.google_api_key,
        )
    if settings.groq_api_key:
        # Fall back to Groq if no Google key
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=settings.groq_model,
            temperature=temperature,
            api_key=settings.groq_api_key,
        )
    raise RuntimeError(
        "No LLM API key found. Set GOOGLE_API_KEY (preferred) or GROQ_API_KEY in .env"
    )


def llm_text(response) -> str:
    """Safely extract plain text from an LLM response.

    The new Gemini SDK returns content as list[dict] like:
        [{'type': 'text', 'text': '...', 'extras': {...}}]
    Older SDKs / Groq return a plain string.
    This helper handles both formats.
    """
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p["text"] for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return "\n".join(parts)
    return str(content)

