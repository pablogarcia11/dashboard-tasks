"""Pull requests abiertas en GitHub: las que piden tu revisión y las tuyas.

Solo lectura, con un token personal en .env (GITHUB_TOKEN). Sin token, la fuente no se usa.
Usa la búsqueda de GitHub con @me, así que no hace falta configurar el usuario.
"""
import os
from datetime import datetime

import httpx
from dotenv import dotenv_values

from collectors.base import Activity
from core.config import ROOT

API = "https://api.github.com"
QUERIES = {   # kind → búsqueda
    "review": "is:pr is:open archived:false review-requested:@me",
    "pr": "is:pr is:open archived:false author:@me",
}


class GithubError(RuntimeError):
    pass


def github_token() -> str:
    return (dotenv_values(ROOT / ".env").get("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()


def pull_requests(items: list[dict], kind: str, today: str) -> list[Activity]:
    """Resultados de /search/issues → Activity (instantánea de hoy, como las tareas de Notion)."""
    out = []
    for it in items:
        repo = it.get("repository_url", "").removeprefix(f"{API}/repos/")
        out.append(Activity(
            source="github", kind=kind, external_id=f"{kind}:{it['id']}", ts=it.get("updated_at", ""),
            work_date=today, title=it.get("title", ""), url=it.get("html_url", ""), project=repo,
            extra={"repo": repo, "number": it.get("number"), "draft": bool(it.get("draft")),
                   "author": (it.get("user") or {}).get("login", ""), "updated": it.get("updated_at", "")},
        ))
    return out


def error_message(status: int, body: str) -> str:
    if status == 401:
        return "El token de GitHub no es válido o ha caducado: crea uno nuevo y cámbialo en .env (GITHUB_TOKEN)"
    if status == 403 and "SAML" in body:
        return "La organización exige autorizar el token con SSO: en GitHub, Settings → Tokens → Configure SSO"
    if status in (403, 429):
        return "GitHub ha limitado las consultas: vuelve a intentarlo en unos minutos"
    return f"GitHub respondió {status}"


class GithubCollector:
    source = "github"

    def __init__(self, token: str, http: httpx.Client | None = None):
        self.http = http or httpx.Client(base_url=API, timeout=30, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"})

    def collect(self) -> dict[str, list[Activity]]:
        today = datetime.now().astimezone().date().isoformat()
        out = {}
        for kind, q in QUERIES.items():
            r = self.http.get("/search/issues", params={"q": q, "per_page": 50, "sort": "updated"})
            if r.status_code != 200:
                raise GithubError(error_message(r.status_code, r.text))
            out[kind] = pull_requests(r.json().get("items", []), kind, today)
        return out
