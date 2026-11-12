"""Entorno con el que se lanza `claude -p` (stand-up y conectores de Calendar/Slack).

- Sin ANTHROPIC_API_KEY: fuerza la suscripción.
- CLAUDE_CONFIG_DIR del .env: quien use Claude Code con una carpeta de configuración propia
  (p. ej. ~/.claude-empresa) la indica ahí; si no, el dashboard usaría la sesión de ~/.claude,
  que puede ser otra cuenta, no tener los conectores o haber caducado.
"""
import os

from dotenv import dotenv_values

from core.config import ROOT


def claude_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    config_dir = (dotenv_values(ROOT / ".env").get("CLAUDE_CONFIG_DIR") or "").strip()
    if config_dir:
        env["CLAUDE_CONFIG_DIR"] = os.path.expandvars(os.path.expanduser(config_dir))
    return env
