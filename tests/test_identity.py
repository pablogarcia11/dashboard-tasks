import json

from core.identity import avatar_path, initials, notion_user_name, resolve_name

CFG = {"user": {"git_authors": ["pablogarcia@1millionbot.com"]}}


def test_usa_la_primera_fuente_con_nombre():
    assert resolve_name(CFG, sources=(lambda: None, lambda: "Pablo García Aljibe")) == "Pablo García Aljibe"
    assert resolve_name(CFG, sources=(lambda: "Pablo García", lambda: "Otro")) == "Pablo García"


def test_sin_fuentes_usa_el_email_y_luego_dashboard(monkeypatch):
    import core.identity as identity
    monkeypatch.setattr(identity, "git_global_email", lambda: None)
    assert resolve_name(CFG, sources=(lambda: None,)) == "pablogarcia"
    assert resolve_name({"user": {}}, sources=(lambda: None,)) == "Dashboard"
    monkeypatch.setattr(identity, "git_global_email", lambda: "ana@empresa.com")
    assert resolve_name({"user": {}}, sources=(lambda: None,)) == "ana"


def test_notion_user_name(tmp_path):
    token = tmp_path / "t.json"
    token.write_text(json.dumps({"owner": {"type": "user", "user": {"name": "Pablo García Aljibe"}}}), encoding="utf-8")
    assert notion_user_name(token) == "Pablo García Aljibe"
    assert notion_user_name(tmp_path / "no-existe.json") is None


def test_avatar_sin_foto_ni_cache(tmp_path):
    token = tmp_path / "t.json"
    token.write_text(json.dumps({"owner": {"user": {"name": "X"}}}), encoding="utf-8")
    assert avatar_path(token, tmp_path / "avatar.img") is None
    cache = tmp_path / "ya.img"
    cache.write_bytes(b"\xff\xd8")
    assert avatar_path(token, cache) == cache   # si ya está en local, no se descarga


def test_initials():
    assert initials("Pablo García") == "PG"
    assert initials("Pablo García Aljibe") == "PG"
    assert initials("pablogarcia") == "P"
