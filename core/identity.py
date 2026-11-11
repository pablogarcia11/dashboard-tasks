"""Nombre de la persona que usa el dashboard, deducido de las herramientas conectadas (nada fijo en código).

Orden: nombre global de git (con el que firma sus commits) → usuario de Notion que autorizó la
conexión → parte local del email de autor configurado → "Dashboard".
"""
import json
import subprocess
from functools import lru_cache
from pathlib import Path

from core.config import ROOT, load_config

NOTION_TOKEN = ROOT / "secrets" / "notion_token.json"


def git_user_name() -> str | None:
    try:
        p = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() or None


def notion_user_name(token_file: Path = NOTION_TOKEN) -> str | None:
    try:
        owner = json.loads(token_file.read_text(encoding="utf-8")).get("owner", {})
    except (OSError, ValueError):
        return None
    return (owner.get("user") or {}).get("name") or None


def email_name(cfg: dict) -> str | None:
    authors = cfg.get("user", {}).get("git_authors") or []
    return authors[0].split("@")[0] if authors else None


def resolve_name(cfg: dict, sources=(git_user_name, notion_user_name)) -> str:
    for source in sources:
        name = source()
        if name:
            return name
    return email_name(cfg) or "Dashboard"


@lru_cache
def display_name() -> str:
    """Nombre para la cabecera (se calcula una vez por arranque)."""
    return resolve_name(load_config())


def initials(name: str) -> str:
    parts = [p for p in name.split() if p[:1].isalpha()]
    return "".join(p[0] for p in parts[:2]).upper() or name[:1].upper()
