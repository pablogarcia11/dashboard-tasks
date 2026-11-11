"""Envoltorio de `claude -p` (Claude Code headless con la suscripción, sin API key).

Claude solo redacta: se lanza sin herramientas ni conectores y recibe el contexto por stdin.
Los resultados se cachean en `summaries` por hash del contexto.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile

from core import db
from core.config import ROOT

PROMPTS = ROOT / "prompts"


class ClaudeError(RuntimeError):
    pass


def run_claude(prompt: str, context: dict, cfg: dict) -> str:
    c = cfg["claude"]
    exe = shutil.which(c.get("command", "claude")) or c.get("command", "claude")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # fuerza la suscripción
    try:
        p = subprocess.run(
            [exe, "-p", prompt, "--output-format", "json", "--model", c.get("model", "sonnet"),
             "--tools", "", "--strict-mcp-config"],
            input=json.dumps(context, ensure_ascii=False), capture_output=True, text=True, encoding="utf-8",
            env=env, timeout=c.get("timeout_seconds", 300), cwd=tempfile.gettempdir(),  # lejos de los repos
        )
    except subprocess.TimeoutExpired:
        raise ClaudeError("Claude no respondió a tiempo")
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise ClaudeError((p.stderr or p.stdout or "respuesta vacía").strip()[:500])
    if out.get("is_error"):
        raise ClaudeError(str(out.get("result") or out.get("subtype") or "error desconocido")[:500])
    return out["result"].strip()


def generate(con: sqlite3.Connection, cfg: dict, kind: str, work_date: str, context: dict,
             force: bool = False) -> tuple[str, bool]:
    """Genera (o devuelve de caché) el texto `kind` para `work_date`. Devuelve (texto, venía_de_caché).

    Si Claude falla (p. ej. límite de cuota) lanza ClaudeError; el último resultado guardado se conserva.
    """
    prompt = (PROMPTS / f"{kind}.md").read_text(encoding="utf-8")
    payload = json.dumps({"prompt": prompt, "context": context, "model": cfg["claude"].get("model")},
                         ensure_ascii=False, sort_keys=True)
    input_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    cached = db.get_summary(con, work_date, kind)
    if cached and cached["input_hash"] == input_hash and not force:
        return cached["content_md"], True
    text = run_claude(prompt, context, cfg)
    db.save_summary(con, work_date, kind, text, input_hash)
    return text, False
