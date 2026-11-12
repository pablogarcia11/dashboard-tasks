"""Búsqueda en el historial guardado: commits, notas y pendientes del diario y reuniones.

Sin distinguir mayúsculas ni tildes («migracion» encuentra «Migración»). Todas las palabras tienen que
aparecer (en el título, el detalle, el repo o el proyecto). Respeta lo oculto en Ajustes.
"""
import re
import sqlite3
import unicodedata

from core import db
from core.views import visible_git

KINDS = {"commit": "Commit", "note": "Nota", "task_plan": "Pendiente", "meeting": "Reunión"}
LIMIT = 200


def fold(s: str) -> str:
    """Minúsculas y sin tildes, misma longitud que el original (para poder resaltar en el texto original)."""
    return "".join(unicodedata.normalize("NFKD", c)[0].lower() if c else c for c in s)


def terms(query: str) -> list[str]:
    return [t for t in fold(query).split() if t]


def search(con: sqlite3.Connection, query: str, limit: int = LIMIT) -> tuple[list[dict], int]:
    """(resultados, total). Los más recientes primero; como mucho `limit`."""
    words = terms(query)
    if not words:
        return [], 0
    acts = [a for a in visible_git(db.activities(con, "0000-00-00", "9999-99-99"), db.repo_settings(con))
            if a["kind"] in KINDS]
    hits = []
    for a in acts:
        haystack = fold(" ".join(filter(None, [a["title"], a["body"], a["project"], a["extra"].get("repo")])))
        if all(w in haystack for w in words):
            hits.append(a)
    hits.sort(key=lambda a: (a["work_date"], a["ts"]), reverse=True)
    return hits[:limit], len(hits)


def highlight(text: str, query: str) -> list[tuple[str, bool]]:
    """Trozos de `text` con los que coinciden con alguna palabra marcados (para pintarlos con <mark>)."""
    words = terms(query)
    if not text or not words:
        return [(text or "", False)]
    folded = fold(text)
    marks = [False] * len(text)
    for w in words:
        for m in re.finditer(re.escape(w), folded):
            for i in range(m.start(), m.end()):
                marks[i] = True
    out: list[tuple[str, bool]] = []
    for ch, on in zip(text, marks):
        if out and out[-1][1] == on:
            out[-1] = (out[-1][0] + ch, on)
        else:
            out.append((ch, on))
    return out
