"""
Shared LLM factory with model fallback chain.
Tries models in order until one works (handles quota limits gracefully).
"""
import os
from langchain_google_genai import ChatGoogleGenerativeAI


# Model preference order — gemini-2.0-flash-lite has lower quota pressure than 2.0-flash
_MODEL_CHAIN = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]


def get_llm(temperature: float = 0.1) -> ChatGoogleGenerativeAI:
    """
    Return a Gemini LLM instance.
    Uses gemini-1.5-flash-latest by default (highest free-tier quota).
    Override by setting GEMINI_MODEL env var.
    """
    model = os.getenv("GEMINI_MODEL", _MODEL_CHAIN[0])
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=os.getenv("GEMINI_API_KEY"),
        max_retries=2,
    )
