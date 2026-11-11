"""Colector de Notion: diario "I'M BACK" y tareas activas de la base "Tareas".

Solo lectura, con el token OAuth de secrets/notion_token.json (ver collectors/notion_auth.py).
"""
import json
import os
import re
import unicodedata
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

from collectors.base import Activity
from core.config import ROOT

TOKEN_FILE = ROOT / "secrets" / "notion_token.json"
API = "https://api.notion.com/v1"
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2,4})")
LIST_TYPES = {"bulleted_list_item", "numbered_list_item", "to_do", "paragraph", "toggle"}


def plain(block: dict) -> str:
    return "".join(t.get("plain_text", "") for t in block.get(block["type"], {}).get("rich_text", [])).strip()


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def parse_day(title: str) -> date | None:
    """'Martes 10/11/2026' -> date(2026, 11, 10)."""
    m = DATE_RE.search(title)
    if not m:
        return None
    d, mth, y = (int(g) for g in m.groups())
    try:
        return date(y + 2000 if y < 100 else y, mth, d)
    except ValueError:
        return None


def is_pending_marker(text: str) -> bool:
    return normalize(text) in {"pendiente", "pendientes"}


class NotionClient:
    def __init__(self):
        load_dotenv(ROOT / ".env")
        self.token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        self.http = httpx.Client(base_url=API, timeout=60)

    def _headers(self):
        return {"Authorization": f"Bearer {self.token['access_token']}", "Notion-Version": "2022-06-28"}

    def _refresh(self) -> bool:
        if not self.token.get("refresh_token"):
            return False
        r = httpx.post(f"{API}/oauth/token", auth=(os.getenv("NOTION_CLIENT_ID"), os.getenv("NOTION_CLIENT_SECRET")),
                       json={"grant_type": "refresh_token", "refresh_token": self.token["refresh_token"]}, timeout=30)
        if r.status_code != 200:
            return False
        self.token = r.json()
        TOKEN_FILE.write_text(json.dumps(self.token, indent=2), encoding="utf-8")
        return True

    def request(self, method: str, path: str, **kw) -> dict:
        r = self.http.request(method, path, headers=self._headers(), **kw)
        if r.status_code == 401 and self._refresh():
            r = self.http.request(method, path, headers=self._headers(), **kw)
        if r.status_code != 200:
            raise RuntimeError(f"Notion {method} {path}: {r.status_code} {r.text[:200]}")
        return r.json()

    def children(self, block_id: str) -> list[dict]:
        out, cursor = [], None
        while True:
            params = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            d = self.request("GET", f"/blocks/{block_id}/children", params=params)
            out += d["results"]
            if not d.get("has_more"):
                return out
            cursor = d["next_cursor"]

    def query_database(self, db_id: str, flt: dict) -> list[dict]:
        out, cursor = [], None
        while True:
            body = {"filter": flt, "page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            d = self.request("POST", f"/databases/{db_id}/query", json=body)
            out += d["results"]
            if not d.get("has_more"):
                return out
            cursor = d["next_cursor"]


def page_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop["title"]).strip() or "Sin título"
    return "Sin título"


def journal_candidates(client: NotionClient, query: str = "", limit: int = 20) -> list[dict]:
    """Páginas compartidas con la conexión que pueden ser un diario (no filas de bases de datos)."""
    found, cursor = [], None
    for _ in range(5):  # la búsqueda mezcla filas de bases de datos: se piden varias tandas
        body = {"filter": {"property": "object", "value": "page"}, "page_size": 100,
                "sort": {"direction": "descending", "timestamp": "last_edited_time"}}
        if query:
            body["query"] = query
        if cursor:
            body["start_cursor"] = cursor
        d = client.request("POST", "/search", json=body)
        for p in d["results"]:
            if p.get("parent", {}).get("type") != "database_id" and not p.get("archived"):
                icon = (p.get("icon") or {}).get("emoji", "")
                found.append({"id": p["id"], "title": page_title(p), "url": p.get("url", ""), "icon": icon})
        if len(found) >= limit or not d.get("has_more"):
            break
        cursor = d["next_cursor"]
    return found[:limit]


def journal_preview(client: NotionClient, page_id: str) -> dict:
    """Cuántos días con el formato esperado (encabezado 1 con dd/mm/aaaa) tiene la página."""
    days = sorted(d for d in (parse_day(plain(b)) for b in client.children(page_id)
                              if b["type"] == "heading_1") if d)
    return {"days": len(days), "first": days[0] if days else None, "last": days[-1] if days else None}


def subtree_text(client: NotionClient, block: dict, depth: int = 0) -> list[str]:
    """Texto de los hijos de un bloque como lista con sangría."""
    lines = []
    if block.get("has_children"):
        for c in client.children(block["id"]):
            t = plain(c)
            if t:
                lines.append("  " * depth + "- " + t)
            lines += subtree_text(client, c, depth + 1)
    return lines


def parse_day_blocks(client: NotionClient, blocks: list[dict]) -> list[tuple[str, str, str, list[str], bool]]:
    """Recorre los hijos de un H1 de día. Devuelve (block_id, proyecto, texto, sublíneas, es_pendiente).

    Estructura: heading_3 = proyecto, seguido de sus viñetas como hermanas. Un bloque "Pendiente:"
    marca como pendientes sus hijos o, si no tiene, las viñetas que le siguen hasta el siguiente H3.
    """
    out, project, pending_mode = [], "", False
    for b in blocks:
        t = b["type"]
        if t in ("heading_1", "heading_2", "heading_3"):
            project, pending_mode = plain(b), False
            continue
        if t not in LIST_TYPES:
            continue
        text = plain(b)
        if is_pending_marker(text):
            if b.get("has_children"):
                for c in client.children(b["id"]):
                    if plain(c):
                        out.append((c["id"], project, plain(c), subtree_text(client, c), True))
            else:
                pending_mode = True
            continue
        if text:
            out.append((b["id"], project, text, subtree_text(client, b), pending_mode))
    return out


class NotionCollector:
    source = "notion"

    def __init__(self, config: dict):
        n = config["notion"]
        self.page_id = n.get("journal_page_id")       # página diario elegida en Ajustes
        self.db_id = n.get("tasks_database_id")
        self.user_id = n.get("user_id")               # de la conexión OAuth (core/settings.py)
        self.person_prop = n.get("tasks_person_property", "Persona Responsable")
        self.inactive = n.get("tasks_inactive_statuses", ["Done", "Archived"])
        self.tz = config["user"]["timezone"]
        self.client = NotionClient()

    def journal_title(self) -> str | None:
        """Título actual de la página diario (por si se renombró en Notion)."""
        if not self.page_id:
            return None
        return page_title(self.client.request("GET", f"/pages/{self.page_id}"))

    def collect_journal(self, start: date, end: date) -> list[Activity]:
        """Notas (kind=note) y pendientes (kind=task_plan) de la página diario entre start y end."""
        if not self.page_id:
            return []
        items = []
        for h1 in self.client.children(self.page_id):
            if h1["type"] != "heading_1":
                continue
            day = parse_day(plain(h1))
            if not day or not (start <= day <= end):
                continue
            ts = datetime.combine(day, time.min, ZoneInfo(self.tz)).isoformat()
            for block_id, project, text, sub, pending in parse_day_blocks(self.client, self.client.children(h1["id"])):
                items.append(Activity(
                    source="notion", kind="task_plan" if pending else "note", external_id=block_id,
                    ts=ts, work_date=day.isoformat(), title=text, body="\n".join(sub), project=project,
                    url=f"https://www.notion.so/{self.page_id.replace('-', '')}#{block_id.replace('-', '')}",
                ))
        return items

    def collect_tasks(self) -> list[Activity]:
        """Tareas activas del usuario (instantánea de hoy)."""
        if not (self.db_id and self.user_id):
            return []
        flt = {"and": [{"property": self.person_prop, "people": {"contains": self.user_id}}]
               + [{"property": "Status", "status": {"does_not_equal": s}} for s in self.inactive]}
        now = datetime.now(ZoneInfo(self.tz))
        items = []
        for p in self.client.query_database(self.db_id, flt):
            pr = p["properties"]
            title = "".join(t["plain_text"] for t in pr.get("Tarea", {}).get("title", []))
            items.append(Activity(
                source="notion", kind="task", external_id=p["id"], ts=now.isoformat(timespec="seconds"),
                work_date=now.date().isoformat(), title=title, url=p["url"],
                status=(pr.get("Status") or {}).get("status", {}).get("name", ""),
                extra={"priority": select_name(pr, "Prioridad"), "type": select_name(pr, "Tipo"),
                       "due": first_date(pr, DUE_PROPS)},
            ))
        return items


DUE_PROPS = ("Fecha límite", "Fecha de Vencimiento", "Fecha Fin", "Fecha")


def select_name(props: dict, key: str) -> str:
    return ((props.get(key) or {}).get("select") or {}).get("name", "")


def first_date(props: dict, keys) -> str | None:
    for k in keys:
        d = (props.get(k) or {}).get("date")
        if d:
            return d.get("start")
    return None
