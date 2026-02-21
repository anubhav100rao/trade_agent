"""
pytest configuration for the trade_agent test suite.

Marks:
  @pytest.mark.unit    — fast, no network, no LLM
  @pytest.mark.llm     — requires a working GEMINI_API_KEY
  @pytest.mark.slow    — spins the full server; takes 1-3 min

Run subsets:
  pytest tests/ -m unit              # fast unit tests only (~5s)
  pytest tests/ -m "unit or slow"    # all tests including server tests
  pytest tests/ -m llm               # LLM-dependent tests only
"""
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--skip-llm", action="store_true", default=False,
        help="Skip tests that require a Gemini API key"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast unit tests, no network or LLM")
    config.addinivalue_line("markers", "llm: requires GEMINI_API_KEY with available quota")
    config.addinivalue_line("markers", "slow: starts the full FastAPI server")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--skip-llm"):
        skip_llm = pytest.mark.skip(reason="--skip-llm passed")
        for item in items:
            if "llm" in item.keywords:
                item.add_marker(skip_llm)
