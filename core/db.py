"""Acceso a SQLite (db/dashboard.db)."""
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from collectors.base import Activity
from core.config import ROOT

DB_PATH = ROOT / "db" / "dashboard.db"
SCHEMA = ROOT / "db" / "schema.sql"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    return con


def upsert_activities(con: sqlite3.Connection, items: list[Activity]) -> int:
    rows = []
    for a in items:
        d = asdict(a)
        d["extra_json"] = json.dumps(d.pop("extra"), ensure_ascii=False)
        rows.append(d)
    con.executemany(
        """INSERT INTO activity (source, kind, external_id, ts, work_date, title, body, url, project, status, extra_json)
           VALUES (:source, :kind, :external_id, :ts, :work_date, :title, :body, :url, :project, :status, :extra_json)
           ON CONFLICT(source, external_id) DO UPDATE SET
             kind=excluded.kind, ts=excluded.ts, work_date=excluded.work_date, title=excluded.title,
             body=excluded.body, url=excluded.url, project=excluded.project, status=excluded.status,
             extra_json=excluded.extra_json""",
        rows,
    )
    con.commit()
    return len(rows)


def replace_kind(con: sqlite3.Connection, source: str, kind: str, items: list[Activity]) -> None:
    """Sustituye todas las entradas de un tipo (p. ej. el WIP, que solo refleja el estado actual)."""
    con.execute("DELETE FROM activity WHERE source = ? AND kind = ?", (source, kind))
    upsert_activities(con, items)


def replace_range(con: sqlite3.Connection, source: str, kinds: list[str], start: str, end: str,
                  items: list[Activity]) -> None:
    """Sustituye las entradas de esos tipos en el rango (p. ej. notas de Notion editadas o borradas)."""
    con.execute(f"DELETE FROM activity WHERE source = ? AND kind IN ({','.join('?' * len(kinds))})"
                " AND work_date BETWEEN ? AND ?", (source, *kinds, start, end))
    upsert_activities(con, items)


def activities(con: sqlite3.Connection, start: str, end: str, sources=None) -> list[dict]:
    """Actividad entre dos work_date (incluidas), ordenada por hora."""
    q = "SELECT * FROM activity WHERE work_date BETWEEN ? AND ?"
    args = [start, end]
    if sources:
        q += f" AND source IN ({','.join('?' * len(sources))})"
        args += list(sources)
    out = []
    for r in con.execute(q + " ORDER BY ts", args):
        d = dict(r)
        d["extra"] = json.loads(d.pop("extra_json") or "{}")
        out.append(d)
    return out


def get_summary(con: sqlite3.Connection, work_date: str, kind: str) -> dict | None:
    r = con.execute("SELECT * FROM summaries WHERE work_date = ? AND kind = ?", (work_date, kind)).fetchone()
    return dict(r) if r else None


def save_summary(con: sqlite3.Connection, work_date: str, kind: str, content: str, input_hash: str) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    con.execute("""INSERT INTO summaries (work_date, kind, content_md, input_hash, created_at) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(work_date, kind) DO UPDATE SET content_md=excluded.content_md,
                   input_hash=excluded.input_hash, created_at=excluded.created_at""",
                (work_date, kind, content, input_hash, now))
    con.commit()


def sync_states(con: sqlite3.Connection) -> dict:
    return {r["source"]: dict(r) for r in con.execute("SELECT * FROM sync_state")}


def set_sync_state(con: sqlite3.Connection, source: str, error: str | None = None) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    if error:
        con.execute("""INSERT INTO sync_state (source, last_error) VALUES (?, ?)
                       ON CONFLICT(source) DO UPDATE SET last_error=excluded.last_error""", (source, error))
    else:
        con.execute("""INSERT INTO sync_state (source, last_ok, last_error) VALUES (?, ?, NULL)
                       ON CONFLICT(source) DO UPDATE SET last_ok=excluded.last_ok, last_error=NULL""", (source, now))
    con.commit()
