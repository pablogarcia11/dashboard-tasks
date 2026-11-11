"""Lectura de herramientas a través de los conectores de la cuenta de Claude (Google Calendar, Slack).

`claude -p` (Haiku) solo puede usar las herramientas de lectura que se le indiquen. Los datos se leen
del tool_result en bruto del stream (tal cual los devuelve el servicio), nunca de la respuesta redactada.
"""
import json
import os
import shutil
import subprocess
import tempfile


class ConnectorError(RuntimeError):
    pass


def run_connector(prompt: str, tools: list[str], claude_cfg: dict) -> str:
    """Ejecuta `claude -p` con esas herramientas permitidas y devuelve el stream-json en bruto."""
    exe = shutil.which(claude_cfg.get("command", "claude")) or claude_cfg.get("command", "claude")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # fuerza la suscripción
    try:
        p = subprocess.run(
            [exe, "-p", prompt, "--model", "haiku", "--allowedTools", ",".join(tools),
             "--output-format", "stream-json", "--verbose"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
            timeout=claude_cfg.get("timeout_seconds", 300), cwd=tempfile.gettempdir(),
        )
    except subprocess.TimeoutExpired:
        raise ConnectorError("Claude no respondió a tiempo")
    return p.stdout


def tool_results(stream: str) -> list[dict]:
    """tool_result de un stream-json de `claude -p`."""
    out = []
    for line in stream.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") != "user":
            continue
        for c in msg.get("message", {}).get("content", []):
            if isinstance(c, dict) and c.get("type") == "tool_result":
                out.append(c)
    return out


def result_text(result: dict) -> str:
    content = result.get("content")
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content or [] if isinstance(c, dict))
