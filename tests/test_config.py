from pathlib import Path

from src.config import ROOT


def test_env_example_exists_without_real_key():
    example = Path(ROOT) / ".env.example"
    text = example.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=your_key_here" in text
    assert "sk-" not in text

