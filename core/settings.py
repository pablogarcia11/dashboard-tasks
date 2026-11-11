"""Ajustes de cada usuario elegidos desde la web (tabla app_settings) y su combinación con config.yaml.

config.yaml queda para lo común (zona horaria, jornada, categorías...). Lo que es propio de cada persona
(su página diario de Notion, la carpeta donde tiene sus repos) se elige en Ajustes y se guarda aquí.
"""
import copy
import json
import sqlite3

from core.identity import notion_owner

JOURNAL_PAGE_ID = "notion.journal_page_id"
JOURNAL_PAGE_TITLE = "notion.journal_page_title"
REPOS_ROOT = "git.repos_root"
EXTRA_AUTHORS = "git.extra_authors"   # JSON: emails de autor añadidos a mano (los de git se detectan solos)
STANDUP_CHANNEL = "standup.channel"    # canal de stand-up de la persona (por defecto, el de config.yaml)
STANDUP_EXAMPLES = "standup.examples"  # JSON: sus últimos stand-ups del canal, para imitar su formato


def extra_authors(con: sqlite3.Connection) -> list[str]:
    try:
        return json.loads(get_all(con).get(EXTRA_AUTHORS) or "[]")
    except ValueError:
        return []


def set_extra_authors(con: sqlite3.Connection, emails: list[str]) -> None:
    set_value(con, EXTRA_AUTHORS, json.dumps(sorted(set(emails))) if emails else None)


def get_all(con: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM app_settings")}


def set_value(con: sqlite3.Connection, key: str, value: str | None) -> None:
    if value is None:
        con.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    else:
        con.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    con.commit()


def effective_config(cfg: dict, con: sqlite3.Connection) -> dict:
    """config.yaml + ajustes del usuario + datos de la conexión de Notion (su id de usuario)."""
    out = copy.deepcopy(cfg)
    saved = get_all(con)
    out.setdefault("git", {})
    out.setdefault("notion", {})
    out.setdefault("user", {})
    manual = (out["user"].get("git_authors") or []) + extra_authors(con)
    if manual:
        out["user"]["git_authors"] = manual
    if saved.get(REPOS_ROOT):
        out["git"]["repos_root"] = saved[REPOS_ROOT]
    if saved.get(JOURNAL_PAGE_ID):
        out["notion"]["journal_page_id"] = saved[JOURNAL_PAGE_ID]
        out["notion"]["journal_page_title"] = saved.get(JOURNAL_PAGE_TITLE) or "Diario"
    owner_id = notion_owner().get("id")
    if owner_id:
        out["notion"]["user_id"] = owner_id
    return out
