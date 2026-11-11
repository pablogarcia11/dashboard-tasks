"""Autorización OAuth de Notion (se ejecuta una vez).

Uso:  python -m collectors.notion_auth

Abre el navegador para que el usuario autorice la conexión "dashboard-personal",
recibe el código en el redirect local y guarda el token en secrets/notion_token.json.
"""
import json
import os
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / "secrets" / "notion_token.json"
AUTHORIZE_URL = "https://api.notion.com/v1/oauth/authorize"
TOKEN_URL = "https://api.notion.com/v1/oauth/token"


def main() -> int:
    load_dotenv(ROOT / ".env")
    client_id = os.getenv("NOTION_CLIENT_ID")
    client_secret = os.getenv("NOTION_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Faltan NOTION_CLIENT_ID o NOTION_CLIENT_SECRET en .env")
        return 1

    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    redirect_uri = config["notion"]["redirect_uri"]
    redirect = urlparse(redirect_uri)
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

    # Solo escucha en local
    server = HTTPServer(("127.0.0.1", redirect.port), Handler)
    auth_url = AUTHORIZE_URL + "?" + urlencode({
        "client_id": client_id,
        "response_type": "code",
        "owner": "user",
        "redirect_uri": redirect_uri,
        "state": state,
    })
    print("Abriendo el navegador para autorizar en Notion...")
    print("Si no se abre, visita:", auth_url)
    webbrowser.open(auth_url)
    server.serve_forever()

    if "code" not in result:
        print("No se pudo autorizar:", result.get("error"))
        return 1

    resp = httpx.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        json={"grant_type": "authorization_code", "code": result["code"], "redirect_uri": redirect_uri},
        timeout=30,
    )
    if resp.status_code != 200:
        print("Error al obtener el token:", resp.status_code, resp.text)
        return 1

    TOKEN_FILE.parent.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(resp.json(), indent=2), encoding="utf-8")
    data = resp.json()
    print(f"Token guardado en {TOKEN_FILE}")
    print("Workspace:", data.get("workspace_name"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
