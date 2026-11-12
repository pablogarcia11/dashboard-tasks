import json

from collectors.claude_connector import run_error
from core import claude_env as ce


def _line(msg: dict) -> str:
    return json.dumps(msg)


def test_run_error_sesion_caducada():
    stream = "\n".join([
        _line({"type": "system", "subtype": "init", "mcp_servers": []}),
        _line({"type": "result", "is_error": True,
               "result": "Failed to authenticate: this login reached its time limit and cannot be renewed."}),
    ])
    assert "claude auth login" in run_error(stream)


def test_run_error_otro_error_se_muestra_tal_cual():
    stream = _line({"type": "result", "is_error": True, "result": "Usage limit reached"})
    assert run_error(stream) == "Usage limit reached"


def test_run_error_sin_error_si_hubo_tool_result():
    stream = "\n".join([
        _line({"type": "user", "message": {"content": [{"type": "tool_result", "content": "{\"events\": []}"}]}}),
        _line({"type": "result", "is_error": True, "result": "algo"}),
    ])
    assert run_error(stream) is None


def test_claude_env_usa_config_dir_del_env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("CLAUDE_CONFIG_DIR=C:\\Users\\yo\\.claude-empresa\n", encoding="utf-8")
    monkeypatch.setattr(ce, "ROOT", tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    env = ce.claude_env()
    assert env["CLAUDE_CONFIG_DIR"] == "C:\\Users\\yo\\.claude-empresa"
    assert "ANTHROPIC_API_KEY" not in env


def test_claude_env_sin_config_dir_no_toca_nada(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("CLAUDE_CONFIG_DIR=\n", encoding="utf-8")
    monkeypatch.setattr(ce, "ROOT", tmp_path)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert "CLAUDE_CONFIG_DIR" not in ce.claude_env()
