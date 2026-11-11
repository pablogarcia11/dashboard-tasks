"""Autorización OAuth de Notion.

Lo normal es conectar desde la web (Ajustes → Notion → "Conectar con Notion"), que usa estas mismas
funciones. Este script es la alternativa por terminal:

Uso:  python -m collectors.notion_auth

Abre el navegador para que el usuario autorice la conexión, recibe el código en el redirect local
y guarda el token en secrets/notion_token.json.
"""
import json
import os
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv

from core.config import ROOT, load_config

TOKEN_FILE = ROOT / "secrets" / "notion_token.json"
AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
TOKEN_URL = "https://api.notion.com/v1/oauth/token"


def client_credentials() -> tuple[str | None, str | None]:
    """Credenciales de la conexión OAuth de Notion (en .env, no en el código)."""
    load_dotenv(ROOT / ".env")
    return os.getenv("NOTION_CLIENT_ID"), os.getenv("NOTION_CLIENT_SECRET")


def redirect_uri() -> str:
    return load_config()["notion"]["redirect_uri"]


def authorize_url(state: str) -> str:
    client_id, _ = client_credentials()
    return AUTHORIZE_URL + "?" + urlencode({
        "client_id": client_id, "response_type": "code", "owner": "user",
        "redirect_uri": redirect_uri(), "state": state,
    })


def exchange_code(code: str) -> dict:
    """Canjea el código de autorización por el token y lo guarda. Lanza RuntimeError si falla."""
    client_id, client_secret = client_credentials()
    resp = httpx.post(TOKEN_URL, auth=(client_id, client_secret), timeout=30,
                      json={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri()})
    if resp.status_code != 200:
        raise RuntimeError(f"Notion respondió {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    TOKEN_FILE.parent.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def main() -> int:
    if not all(client_credentials()):
        print("Faltan NOTION_CLIENT_ID o NOTION_CLIENT_SECRET en .env")
        return 1

    redirect = urlparse(redirect_uri())
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path != redirect.path:
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(url.query)
            if params.get("state", [None])[0] != state:
                result["error"] = "state no coincide"
            elif "error" in params:
                result["error"] = params["error"][0]
            else:
                result["code"] = params.get("code", [None])[0]
            ok = "code" in result
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Autorizado. Ya puedes cerrar esta pestaña." if ok else f"Error: {result.get('error')}"
            self.wfile.write(f"<p>{msg}</p>".encode("utf-8"))
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, *args):
            pass

    # Solo escucha en local (el dashboard tiene que estar parado: usa el mismo puerto)
    server = HTTPServer(("127.0.0.1", redirect.port), Handler)
    auth_url = authorize_url(state)
    print("Abriendo el navegador para autorizar en Notion...")
    print("Si no se abre, visita:", auth_url)
    webbrowser.open(auth_url)
    server.serve_forever()

    if "code" not in result:
        print("No se pudo autorizar:", result.get("error"))
        return 1
    try:
        data = exchange_code(result["code"])
    except RuntimeError as e:
        print("Error al obtener el token:", e)
        return 1
    print(f"Token guardado en {TOKEN_FILE}")
    print("Workspace:", data.get("workspace_name"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
