import os

from leadscout.config import load_dotenv
from leadscout.envfile import mask, read_env, update_env

SAMPLE = """# --- AI writer ---
GEMINI_API_KEY=            # free: https://aistudio.google.com/apikey
SMTP_HOST=smtp.gmail.com
SMTP_PASSWORD="abcd efgh ijkl mnop"
CUSTOM_THING=keep-me
"""


def test_read_env_handles_inline_comments_and_quotes(tmp_path):
    p = tmp_path / ".env"
    p.write_text(SAMPLE)
    v = read_env(p)
    assert v["GEMINI_API_KEY"] == ""  # the comment is not the key
    assert v["SMTP_PASSWORD"] == "abcd efgh ijkl mnop"
    assert v["CUSTOM_THING"] == "keep-me"


def test_load_dotenv_does_not_turn_comments_into_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    p = tmp_path / ".env"
    p.write_text(SAMPLE)
    load_dotenv(p)
    assert os.environ.get("GEMINI_API_KEY") == ""
    from leadscout.llm.base import get_llm
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert get_llm("auto") is None  # templates, not a bogus Gemini call


def test_update_env_keeps_comments_and_unknown_keys(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text(SAMPLE)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    update_env(p, {"GEMINI_API_KEY": "AIza-new-key", "SMTP_PASSWORD": None, "GROQ_API_KEY": "gsk_123"})
    text = p.read_text()
    assert "# --- AI writer ---" in text and "CUSTOM_THING=keep-me" in text
    assert "GEMINI_API_KEY=AIza-new-key  # free: https://aistudio.google.com/apikey" in text
    v = read_env(p)
    assert v["GEMINI_API_KEY"] == "AIza-new-key" and v["SMTP_PASSWORD"] == "" and v["GROQ_API_KEY"] == "gsk_123"
    assert os.environ["GEMINI_API_KEY"] == "AIza-new-key"
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


def test_auto_llm_never_picks_paid_claude(monkeypatch):
    from leadscout.llm.base import get_llm
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OLLAMA_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert get_llm("auto") is None


def test_mask():
    assert mask("AIzaSyD-1234567890abcd") == "••••abcd"
    assert mask("short") == "••••" and mask("") == ""
