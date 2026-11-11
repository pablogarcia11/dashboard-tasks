"""Ajustes de cada usuario elegidos desde la web (tabla app_settings) y su combinación con config.yaml.

config.yaml queda para lo común (zona horaria, jornada, categorías...). Lo que es propio de cada persona
(su página diario de Notion, la carpeta donde tiene sus repos) se elige en Ajustes y se guarda aquí.
"""
import copy
import sqlite3

from core.identity import notion_owner

JOURNAL_PAGE_ID = "notion.journal_page_id"
JOURNAL_PAGE_TITLE = "notion.journal_page_title"
REPOS_ROOT = "git.repos_root"


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
    if saved.get(REPOS_ROOT):
        out["git"]["repos_root"] = saved[REPOS_ROOT]
    if saved.get(JOURNAL_PAGE_ID):
        out["notion"]["journal_page_id"] = saved[JOURNAL_PAGE_ID]
        out["notion"]["journal_page_title"] = saved.get(JOURNAL_PAGE_TITLE) or "Diario"
    owner_id = notion_owner().get("id")
    if owner_id:
        out["notion"]["user_id"] = owner_id
    return out
