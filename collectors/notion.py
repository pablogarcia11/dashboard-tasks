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
LIST_TYPES = {"bulleted_list_item", "numbered_list_item", "to_do", "paragraph", "toggle"}
HEADINGS = {"heading_1": 1, "heading_2": 2, "heading_3": 3}

# Fechas que se reconocen en el título de un día del diario
NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")            # 10/11/2026, 10-11-26
ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")                           # 2026-11-10
MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
          "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
MONTH_ABBR = {m[:3]: n for m, n in MONTHS.items()}
WORD_DATE = re.compile(r"\b(\d{1,2})\s+(?:de\s+)?([a-z]{3,10})\.?(?:\s+(?:de\s+|del\s+)?(\d{4}))?\b")
# «Pendiente:», «Para mañana:»… marcan lo que queda para el día siguiente
PENDING_MARKERS = {"pendiente", "pendientes", "para manana", "manana", "por hacer", "todo", "to do"}


def plain(block: dict) -> str:
    return "".join(t.get("plain_text", "") for t in block.get(block["type"], {}).get("rich_text", [])).strip()


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def _date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y + 2000 if y < 100 else y, m, d)
    except ValueError:
        return None


def parse_day(title: str, today: date | None = None) -> date | None:
    """Fecha de un título de día: «Martes 10/11/2026», «2026-11-10», «10 de noviembre de 2026»,
    «10 nov 2026» o «Martes 10 de noviembre» (sin año: el más reciente que no quede en el futuro)."""
    if m := ISO_DATE.search(title):
        return _date(int(m[1]), int(m[2]), int(m[3]))
    if m := NUMERIC_DATE.search(title):
        return _date(int(m[3]), int(m[2]), int(m[1]))
    for m in WORD_DATE.finditer(normalize(title)):
        month = MONTHS.get(m[2]) or MONTH_ABBR.get(m[2][:3])
        if not month:
            continue
        if m[3]:
            return _date(int(m[3]), month, int(m[1]))
        today = today or date.today()
        d = _date(today.year, month, int(m[1]))
        if d and (d - today).days > 31:   # «28 de diciembre» leído en enero es del año pasado
            d = _date(today.year - 1, month, int(m[1]))
        return d
    return None


def block_date(block: dict, today: date | None = None) -> date | None:
    """Fecha de un bloque: una mención de fecha de Notion (@10 nov 2026) o una fecha escrita."""
    t = block["type"]
    if t == "child_page":
        return parse_day(block["child_page"].get("title", ""), today)
    for rt in block.get(t, {}).get("rich_text", []):
        start = ((rt.get("mention") or {}).get("date") or {}).get("start")
        if start:
            return date.fromisoformat(start[:10])
    return parse_day(plain(block), today)


def is_pending_marker(text: str) -> bool:
    return normalize(text) in PENDING_MARKERS


def inline_pending(text: str) -> str | None:
    """Texto del pendiente escrito en la misma línea que su marca («Pendiente: probar el flujo»),
    o None si la línea no es eso. Hacen falta los dos puntos: «Pendiente de revisar…» es una nota."""
    head, sep, rest = text.partition(":")
    return rest.strip() if sep and rest.strip() and is_pending_marker(head) else None


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

    def query_database(self, db_id: str, flt: dict | None) -> list[dict]:
        out, cursor = [], None
        while True:
            body = {"page_size": 100, **({"filter": flt} if flt else {}), **({"start_cursor": cursor} if cursor else {})}
            d = self.request("POST", f"/databases/{db_id}/query", json=body)
            out += d["results"]
            if not d.get("has_more"):
                return out
            cursor = d["next_cursor"]


def page_title(page: dict) -> str:
    if page.get("object") == "database":
        return "".join(t.get("plain_text", "") for t in page.get("title", [])).strip() or "Sin título"
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop["title"]).strip() or "Sin título"
    return "Sin título"


def journal_candidates(client: NotionClient, query: str = "", limit: int = 20) -> list[dict]:
    """Páginas y bases de datos compartidas que pueden ser un diario (sin las filas de bases de datos)."""
    found, cursor = [], None
    for _ in range(5):  # la búsqueda mezcla filas de bases de datos: se piden varias tandas
        body = {"page_size": 100, "sort": {"direction": "descending", "timestamp": "last_edited_time"}}
        if query:
            body["query"] = query
        if cursor:
            body["start_cursor"] = cursor
        d = client.request("POST", "/search", json=body)
        for p in d["results"]:
            if p.get("parent", {}).get("type") != "database_id" and not p.get("archived"):
                icon = (p.get("icon") or {}).get("emoji", "")
                found.append({"id": p["id"], "title": page_title(p), "url": p.get("url", ""), "icon": icon,
                              "kind": "database" if p.get("object") == "database" else "page"})
        if len(found) >= limit or not d.get("has_more"):
            break
        cursor = d["next_cursor"]
    return found[:limit]


def day_sections(client: NotionClient, blocks: list[dict], wanted=lambda d: True, today=None
                 ) -> list[tuple[date, list[dict] | None, str | None]]:
    """Días de una página diario: (fecha, bloques del día, id de la página hija si el día es una).
    Un día puede ser:
    - un encabezado (de cualquier nivel) o desplegable con fecha y el contenido dentro;
    - un encabezado con fecha seguido del contenido, hasta el siguiente día de su nivel o superior;
    - una página hija con la fecha en el título.
    Solo se descarga el contenido de los días que `wanted(fecha)` acepta (el resto va como None)."""
    sections, i = [], 0
    while i < len(blocks):
        b, t = blocks[i], blocks[i]["type"]
        short_para = t == "paragraph" and len(plain(b)) <= 40
        d = block_date(b, today) if (t in HEADINGS or t in ("toggle", "child_page") or short_para) else None
        if d is None:
            i += 1
            continue
        if b.get("has_children") or t == "child_page":
            sections.append((d, client.children(b["id"]) if wanted(d) else None,
                             b["id"] if t == "child_page" else None))
            i += 1
            continue
        level, j = HEADINGS.get(t, 4), i + 1   # encabezado sin desplegar: su contenido son los hermanos
        while j < len(blocks):   # ...hasta el siguiente día (página hija, desplegable o encabezado de su nivel)
            nb, nt = blocks[j], blocks[j]["type"]
            if (nt in ("child_page", "toggle") or HEADINGS.get(nt, 9) <= level) and block_date(nb, today):
                break
            j += 1
        sections.append((d, blocks[i + 1:j] if wanted(d) else None, None))
        i = j
    return sections


def journal_kind(client: NotionClient, journal_id: str) -> str:
    """'page' o 'database' (un diario puede ser una base de datos con una página por día)."""
    try:
        client.request("GET", f"/pages/{journal_id}")
        return "page"
    except RuntimeError:
        client.request("GET", f"/databases/{journal_id}")
        return "database"


def database_days(client: NotionClient, db_id: str, today=None) -> list[tuple[date, dict]]:
    """Páginas de un diario-base de datos con su fecha (propiedad de fecha o fecha en el título)."""
    schema = client.request("GET", f"/databases/{db_id}")
    date_prop = next((n for n, p in schema["properties"].items() if p["type"] == "date"), None)
    out = []
    for page in client.query_database(db_id, None):
        d = None
        if date_prop and (page["properties"][date_prop].get("date") or {}).get("start"):
            d = date.fromisoformat(page["properties"][date_prop]["date"]["start"][:10])
        d = d or parse_day(page_title(page), today)
        if d:
            out.append((d, page))
    return out


def journal_preview(client: NotionClient, journal_id: str) -> dict:
    """Cuántos días reconoce el dashboard en el diario y con qué formato."""
    if journal_kind(client, journal_id) == "database":
        days, fmt = sorted(d for d, _ in database_days(client, journal_id)), "una página por día (base de datos)"
    else:
        sections = day_sections(client, client.children(journal_id), wanted=lambda d: False)
        days = sorted(d for d, _, _ in sections)
        fmt = "una página por día" if any(page for _, _, page in sections) else "un encabezado por día"
    return {"days": len(days), "first": days[0] if days else None, "last": days[-1] if days else None,
            "format": fmt}


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


GENERAL = "General"   # proyecto de lo apuntado sin ningún proyecto encima


def parse_day_blocks(client: NotionClient, blocks: list[dict], project: str = ""
                     ) -> list[tuple[str, str, str, list[str], bool]]:
    """Recorre el contenido de un día. Devuelve (block_id, proyecto, texto, sublíneas, es_pendiente).

    - Proyecto: un encabezado (lo que le sigue es de ese proyecto) o un desplegable/encabezado
      desplegable con el proyecto como título y sus tareas dentro. Sin proyecto: «General».
    - Pendiente: un apartado «Pendiente:» / «Para mañana:»… (sus hijos o, si no tiene, lo que le sigue
      hasta el siguiente proyecto), una línea «Pendiente: lo que sea» y las casillas sin marcar. Las casillas marcadas son trabajo hecho.
    """
    out, current, pending_mode = [], project, False
    for b in blocks:
        t, text = b["type"], plain(b)
        if is_pending_marker(text):
            if b.get("has_children"):
                for c in client.children(b["id"]):
                    if plain(c):
                        out.append((c["id"], current or GENERAL, plain(c), subtree_text(client, c), True))
            else:
                pending_mode = True
            continue
        is_heading = t in HEADINGS
        if is_heading or (t == "toggle" and b.get("has_children")):
            if b.get("has_children"):   # proyecto desplegable: sus tareas están dentro
                out += parse_day_blocks(client, client.children(b["id"]), text)
            else:
                current, pending_mode = text, False
            continue
        if t not in LIST_TYPES or not text:
            continue
        inline = inline_pending(text)
        pending = pending_mode or inline is not None or (t == "to_do" and not b["to_do"].get("checked"))
        out.append((b["id"], current or GENERAL, inline or text, subtree_text(client, b), pending))
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
        """Título actual del diario (por si se renombró en Notion)."""
        if not self.page_id:
            return None
        if journal_kind(self.client, self.page_id) == "database":
            return page_title(self.client.request("GET", f"/databases/{self.page_id}"))
        return page_title(self.client.request("GET", f"/pages/{self.page_id}"))

    def journal_days(self, start: date, end: date) -> list[tuple[date, list[dict], str]]:
        """(fecha, bloques del día, página donde está) de los días del diario entre start y end."""
        wanted = lambda d: start <= d <= end
        if journal_kind(self.client, self.page_id) == "database":
            return [(d, self.client.children(p["id"]), p["id"])
                    for d, p in database_days(self.client, self.page_id) if wanted(d)]
        sections = day_sections(self.client, self.client.children(self.page_id), wanted)
        return [(d, blocks, page or self.page_id) for d, blocks, page in sections if blocks is not None]

    def collect_journal(self, start: date, end: date) -> list[Activity]:
        """Notas (kind=note) y pendientes (kind=task_plan) del diario entre start y end."""
        if not self.page_id:
            return []
        items = []
        for day, blocks, page_id in self.journal_days(start, end):
            ts = datetime.combine(day, time.min, ZoneInfo(self.tz)).isoformat()
            for block_id, project, text, sub, pending in parse_day_blocks(self.client, blocks):
                items.append(Activity(
                    source="notion", kind="task_plan" if pending else "note", external_id=block_id,
                    ts=ts, work_date=day.isoformat(), title=text, body="\n".join(sub), project=project,
                    url=f"https://www.notion.so/{page_id.replace('-', '')}#{block_id.replace('-', '')}",
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
                       "due": first_date(pr, DUE_PROPS),
                       # color del estado en Notion (blue, orange, default…) para pintar la etiqueta igual
                       "status_color": ((pr.get("Status") or {}).get("status") or {}).get("color", "default")},
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
