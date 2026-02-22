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

class MockResponse:
    def __init__(self, content):
        self.content = content

class FakeLLM:
    """A minimal mock LLM for integration testing."""
    def invoke(self, messages, **kwargs):
        import re
        prompt = str(messages)
        
        # Try to extract ticker from the last message (HumanMessage) to echo it back
        # This avoids matching tickers listed in the SystemMessage instructions
        user_msg = str(messages[-1].content) if messages else prompt
        match = re.search(r'\b(reliance|infy|tatamotors|hdfcbank|nifty)\b', user_msg, re.IGNORECASE)
        ticker = match.group(1).upper() if match else "RELIANCE"

        # 1. Technical Analyst returns Python code
        if "Write a Python snippet" in prompt or "pd.DataFrame" in prompt:
            code = f"""
```python
result = {{
    "rsi": 58.4,
    "macd": 1.2,
    "macd_signal": "bullish_crossover",
    "bb_position": "neutral"
}}
```
"""
            return MockResponse(code)
            
        # 2. Router / Synthesis / Fundamental / Sentiment (all expect JSON)
        # We craft a mega-JSON that satisfies all Pydantic schemas.
        json_resp = f"""
        ```json
        {{
          "ticker": "{ticker}",
          "analysis_type": "composite",
          "signal": "BUY",
          "confidence": 0.8,
          "summary": "Mock summary for {ticker}",
          "reasoning": "Mock reasoning referencing RSI at 58 and MACD. The PE ratio is 20.",
          "positive_highlights": ["Mock highlight"],
          "red_flags": [],
          "management_sentiment": "positive",
          "score": 0.5,
          "label": "POSITIVE",
          "headline_count": 8
        }}
        ```
        """
        return MockResponse(json_resp)

    def with_structured_output(self, schema, **kwargs):
        # langchain_google_genai's with_structured_output wraps the LLM. 
        # When called, we can just return a class that mocks invoke.
        class StructuredMock:
            def __init__(self, parent_llm):
                self.parent_llm = parent_llm
            def invoke(self, messages, **kwargs):
                # We return the JSON string but parse it into dict/pydantic since with_structured_output expects an object
                resp = self.parent_llm.invoke(messages, **kwargs)
                import json
                text = resp.content.strip().replace("```json", "").replace("```", "").strip()
                data = json.loads(text)
                if hasattr(schema, "model_validate"):
                    return schema.model_validate(data)
                return data
        return StructuredMock(self)


def get_llm(temperature: float = 0.1) -> ChatGoogleGenerativeAI:
    """
    Return a Gemini LLM instance.
    Uses gemini-1.5-flash-latest by default (highest free-tier quota).
    Override by setting GEMINI_MODEL env var.
    """
    if os.getenv("MOCK_LLM") == "true":
        return FakeLLM()
        
    model = os.getenv("GEMINI_MODEL", _MODEL_CHAIN[0])
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=os.getenv("GEMINI_API_KEY"),
        max_retries=2,
    )
