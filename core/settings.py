"""Ajustes de cada usuario elegidos desde la web (tabla app_settings) y su combinación con config.yaml.

config.yaml queda para lo común (zona horaria, jornada, categorías...). Lo que es propio de cada persona
(su página diario de Notion, las carpetas donde tiene sus repos) se elige en Ajustes y se guarda aquí.
"""
import copy
import json
import sqlite3

from dotenv import dotenv_values

from core.config import ROOT
from core.identity import notion_owner

JOURNAL_PAGE_ID = "notion.journal_page_id"
JOURNAL_PAGE_TITLE = "notion.journal_page_title"
REPOS_ROOTS = "git.repos_roots"      # JSON: carpetas donde la persona tiene sus repos (pueden ser varias)
REPOS_ROOT = "git.repos_root"        # antigua, de cuando solo había una carpeta: se migra a REPOS_ROOTS
EXTRA_AUTHORS = "git.extra_authors"   # JSON: emails de autor añadidos a mano (los de git se detectan solos)
STANDUP_CHANNEL = "standup.channel"    # canal de stand-up de la persona (sin él, formato por defecto)
# Horario del parte de horas de la persona (por defecto, el de la empresa en config.yaml)
TIMESHEET_KEYS = ("day_start", "day_end", "lunch_start", "lunch_end", "min_daily_hours")
STANDUP_EXAMPLES = "standup.examples"  # JSON: sus últimos stand-ups del canal, para imitar su formato


DAYS_OFF = "schedule.days_off"      # JSON: festivos y vacaciones de la persona (fechas ISO), además de los de config.yaml


def days_off(con: sqlite3.Connection) -> list[str]:
    try:
        return sorted(set(json.loads(get_all(con).get(DAYS_OFF) or "[]")))
    except ValueError:
        return []


def set_days_off(con: sqlite3.Connection, days: list[str]) -> None:
    set_value(con, DAYS_OFF, json.dumps(sorted(set(days))) if days else None)


def extra_authors(con: sqlite3.Connection) -> list[str]:
    try:
        return json.loads(get_all(con).get(EXTRA_AUTHORS) or "[]")
    except ValueError:
        return []


def set_extra_authors(con: sqlite3.Connection, emails: list[str]) -> None:
    set_value(con, EXTRA_AUTHORS, json.dumps(sorted(set(emails))) if emails else None)


def repos_roots(con: sqlite3.Connection) -> list[str]:
    saved = get_all(con)
    try:
        roots = json.loads(saved.get(REPOS_ROOTS) or "[]")
    except ValueError:
        roots = []
    return roots or ([saved[REPOS_ROOT]] if saved.get(REPOS_ROOT) else [])


def set_repos_roots(con: sqlite3.Connection, roots: list[str]) -> None:
    set_value(con, REPOS_ROOTS, json.dumps(list(dict.fromkeys(roots))) if roots else None)
    set_value(con, REPOS_ROOT, None)


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
    roots = repos_roots(con)
    if roots:
        out["git"]["repos_roots"] = roots
    if saved.get(JOURNAL_PAGE_ID):
        out["notion"]["journal_page_id"] = saved[JOURNAL_PAGE_ID]
        out["notion"]["journal_page_title"] = saved.get(JOURNAL_PAGE_TITLE) or "Diario"
    for k in TIMESHEET_KEYS:
        if saved.get(f"timesheet.{k}"):
            v = saved[f"timesheet.{k}"]
            out.setdefault("timesheet", {})[k] = float(v) if k == "min_daily_hours" else v
    # Base de datos de tareas de Notion: va en .env (no se versiona), junto con las credenciales OAuth
    tasks_db = (dotenv_values(ROOT / ".env").get("NOTION_TASKS_DATABASE_ID") or "").strip()
    if tasks_db:
        out["notion"]["tasks_database_id"] = tasks_db
    owner_id = notion_owner().get("id")
    if owner_id:
        out["notion"]["user_id"] = owner_id
    return out
