"""Lectura del canal de stand-up de Slack (conector de la cuenta de Claude) para aprender el formato
con el que cada persona escribe su stand-up. Solo lectura: buscar el canal y leer sus mensajes.
"""
import json
import re

from collectors.claude_connector import ConnectorError, result_text, run_connector, tool_results

SEARCH_CHANNELS = "mcp__claude_ai_Slack__slack_search_channels"
READ_CHANNEL = "mcp__claude_ai_Slack__slack_read_channel"
# El conector devuelve los mensajes en uno de dos formatos (según la petición):
#  a) «Nombre <email>: texto… [2026-11-11 09:18:04 CET]», separados por una línea en blanco
#  b) «=== Message from Nombre <email> (U123) at 2026-11-11 09:18:04 CET === » + «Message TS: …» + texto
MESSAGE_START = re.compile(r"\n\n(?=[^\n<>]+ <[^>\s]+@[^>\s]+>: )")
MESSAGE = re.compile(r"(?s)^(?P<name>[^\n<>]+) <(?P<email>[^>\s]+)>: (?P<text>.*?)"
                     r"(?: \[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?[^\]]*)\])?\s*$")
HEADER = re.compile(r"=== Message from (?P<name>[^<\n]+?) <(?P<email>[^>\s]+)>(?: \([^)\n]*\))?"
                    r" at (?P<ts>[^=\n]+?) ===[ \t]*\n")


def parse_messages(raw: str) -> list[dict]:
    """Mensajes del texto que devuelve slack_read_channel (tras la cabecera «Channel: …»)."""
    headers = list(HEADER.finditer(raw))
    if headers:   # formato b
        out = []
        for i, h in enumerate(headers):
            body = raw[h.end(): headers[i + 1].start() if i + 1 < len(headers) else len(raw)]
            lines = body.strip("\n").split("\n")
            if lines and lines[0].startswith("Message TS:"):
                lines = lines[1:]
            out.append({"name": h["name"].strip(), "email": h["email"].lower(),
                        "text": "\n".join(lines).strip(), "ts": h["ts"].strip()})
        return out
    out = []   # formato a
    for chunk in MESSAGE_START.split("\n\n" + raw.strip()):
        m = MESSAGE.match(chunk.strip())
        if m:
            out.append({"name": m["name"].strip(), "email": m["email"].lower(),
                        "text": m["text"].strip(), "ts": m["ts"] or ""})
    return out


def messages_from_stream(stream: str) -> list[dict]:
    for r in reversed(tool_results(stream)):   # el último tool_result es la lectura del canal
        text = result_text(r)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("messages"), str):
            return parse_messages(data["messages"])
    raise ConnectorError("Slack no devolvió mensajes del canal (¿conector desconectado o canal inexistente?)")


def own_standups(messages: list[dict], emails: set[str], n: int = 3) -> list[str]:
    """Los n stand-ups más recientes de esa persona (reconocida por cualquiera de sus emails)."""
    mine = [m for m in messages if m["email"] in emails and len(m["text"]) > 40]
    mine.sort(key=lambda m: m["ts"], reverse=True)
    return [m["text"] for m in mine[:n]]


def fetch_channel_messages(channel: str, claude_cfg: dict, limit: int = 50) -> list[dict]:
    prompt = (f"Busca el canal «{channel}» con slack_search_channels y lee sus últimos {limit} mensajes con "
              "slack_read_channel. No uses ninguna otra herramienta de Slack y responde solo 'hecho'.")
    stream = run_connector(prompt, ["ToolSearch", SEARCH_CHANNELS, READ_CHANNEL], claude_cfg)
    return messages_from_stream(stream)
