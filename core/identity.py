"""Nombre y foto de la persona que usa el dashboard, deducidos de las herramientas conectadas (nada fijo en código).

Nombre: usuario de Notion que autorizó la conexión → nombre global de git (con el que firma sus commits)
→ parte local del email de autor configurado → "Dashboard".
Foto: la de perfil de ese usuario de Notion; si no hay, la cabecera muestra sus iniciales.
"""
import json
import subprocess
from functools import lru_cache
from pathlib import Path

import httpx

from core.config import ROOT, load_config

NOTION_TOKEN = ROOT / "secrets" / "notion_token.json"
AVATAR_CACHE = ROOT / "db" / "avatar.img"   # copia local de la foto (fuera de git)


def notion_owner(token_file: Path = NOTION_TOKEN) -> dict:
    try:
        owner = json.loads(token_file.read_text(encoding="utf-8")).get("owner", {})
    except (OSError, ValueError):
        return {}
    return owner.get("user") or {}


def notion_user_name(token_file: Path = NOTION_TOKEN) -> str | None:
    return notion_owner(token_file).get("name") or None


def git_user_name() -> str | None:
    try:
        p = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() or None


def email_name(cfg: dict) -> str | None:
    authors = cfg.get("user", {}).get("git_authors") or []
    return authors[0].split("@")[0] if authors else None


def resolve_name(cfg: dict, sources=(notion_user_name, git_user_name)) -> str:
    for source in sources:
        name = source()
        if name:
            return name
    return email_name(cfg) or "Dashboard"


@lru_cache
def display_name() -> str:
    """Nombre para la cabecera (se calcula una vez por arranque)."""
    return resolve_name(load_config())


def avatar_path(token_file: Path = NOTION_TOKEN, cache: Path = AVATAR_CACHE) -> Path | None:
    """Foto de perfil de Notion, descargada una vez y servida desde local (funciona sin conexión)."""
    if cache.is_file():
        return cache
    url = notion_owner(token_file).get("avatar_url")
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    if not r.headers.get("content-type", "").startswith("image/"):
        return None
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(r.content)
    return cache


def initials(name: str) -> str:
    parts = [p for p in name.split() if p[:1].isalpha()]
    return "".join(p[0] for p in parts[:2]).upper() or name[:1].upper()
