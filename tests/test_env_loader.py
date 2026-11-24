"""Tests for the gitignored .env loader."""
from __future__ import annotations

import os

from reporter.env_loader import load_env


def test_load_env_reads_keys_and_ignores_comments(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_ATTACKER_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# secret keys\n\nGROQ_ATTACKER_KEY='test-key'\nQUOTED=value\nNO_EQUALS\n",
        encoding="utf-8",
    )
    assert load_env(env_file) == 2
    assert os.getenv("GROQ_ATTACKER_KEY") == "test-key"


def test_real_environment_wins_over_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_ATTACKER_KEY", "shell-wins")
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_ATTACKER_KEY=file-value\n", encoding="utf-8")
    assert load_env(env_file) == 0
    assert os.getenv("GROQ_ATTACKER_KEY") == "shell-wins"
