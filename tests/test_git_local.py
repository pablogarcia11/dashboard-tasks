from pathlib import Path

from collectors.git_local import RS, US, discover_repos, parse_log, project_for, short_ref

PROJECTS = {"AI Risk": ["airisk-api", "airisk-api-cdu"], "Aurea": ["aurea"]}


def make_repo(path: Path, worktree: bool = False):
    path.mkdir(parents=True)
    if worktree:
        (path / ".git").write_text("gitdir: C:/x/.git/worktrees/y\n", encoding="utf-8")
    else:
        (path / ".git").mkdir()
        (path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")


def test_discover_repos(tmp_path):
    make_repo(tmp_path / "airisk-api")
    make_repo(tmp_path / "airisk-api-cdu", worktree=True)
    (tmp_path / "aurea" / ".git").mkdir(parents=True)  # .git vacío: no es repo
    make_repo(tmp_path / "aurea" / "aurea-api")
    make_repo(tmp_path / "dashboard")                  # excluido
    make_repo(tmp_path / "millie" / "dashboard")       # mismo nombre, no excluido
    make_repo(tmp_path / "a" / "b" / "c" / "d")        # demasiado profundo
    (tmp_path / "carpeta-normal").mkdir()

    repos = discover_repos(tmp_path, 3, [str(tmp_path / "dashboard")], PROJECTS)
    found = {r.path.relative_to(tmp_path).as_posix(): r for r in repos}

    assert set(found) == {"airisk-api", "airisk-api-cdu", "aurea/aurea-api", "millie/dashboard"}
    assert found["airisk-api-cdu"].is_worktree
    assert found["airisk-api"].project == "AI Risk"
    assert found["aurea/aurea-api"].project == "Aurea"
    assert found["millie/dashboard"].project == "millie"  # sin mapear: carpeta de primer nivel


def test_project_for_no_confunde_prefijos(tmp_path):
    assert project_for(tmp_path / "airisk-api-roles", tmp_path, PROJECTS) == "airisk-api-roles"


def test_project_for_por_nombre_de_repo_o_carpeta_en_cualquier_sitio(tmp_path):
    company = {"AI Risk": ["airisk*"], "Millie": ["millie", "apiREST"], "IBH": ["ibh", "ibh-*"]}
    p = lambda rel: project_for(tmp_path / rel, tmp_path, company)
    assert p("airiskmanagement") == "AI Risk"
    assert p("trabajo/clientes/airisk-api") == "AI Risk"           # da igual dónde esté
    assert p("millie/dashboard") == "Millie"                       # por la carpeta que lo contiene
    assert p("apiREST") == "Millie"                                # por el nombre del repo, sin carpeta millie
    assert p("ibh/bff-user-control-panel") == "IBH"
    assert p("Kanvas") == "Kanvas"                                 # sin patrón: su carpeta de primer nivel


def test_parse_log():
    out = (
        f"{RS}abc123{US}Laura Martín{US}laura.martin@empresa.com{US}2026-11-10T10:15:00+01:00"
        f"{US}refs/heads/laura/roles{US}Corregir permisos\n\n 3 files changed, 40 insertions(+), 2 deletions(-)\n"
        f"{RS}def456{US}lauramartin{US}laura.martin@empresa.com{US}2026-11-10T12:00:00+01:00"
        f"{US}refs/remotes/origin/main{US}Docs: separador {US} raro\n\n 1 file changed, 1 insertion(+)\n"
    )
    first, second = parse_log(out)
    assert first == {"sha": "abc123", "author": "Laura Martín", "email": "laura.martin@empresa.com",
                     "date": "2026-11-10T10:15:00+01:00", "subject": "Corregir permisos",
                     "branch": "laura/roles", "files": 3, "insertions": 40, "deletions": 2}
    assert second["subject"] == f"Docs: separador {US} raro"
    assert second["branch"] == "origin/main"
    assert (second["files"], second["insertions"], second["deletions"]) == (1, 1, 0)


def test_el_propio_dashboard_siempre_se_excluye():
    from collectors.git_local import GitLocalCollector
    from core.config import ROOT
    cfg = {"git": {"repos_root": str(ROOT.parent)}, "user": {"git_authors": ["a@b"], "timezone": "Europe/Madrid"}}
    assert str(ROOT) in GitLocalCollector(cfg).exclude


def test_varias_carpetas_de_repos(tmp_path):
    import subprocess
    from collectors.git_local import GitLocalCollector

    def init(path: Path):
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(path)], check=True)

    a, b = tmp_path / "trabajo", tmp_path / "otro-disco"
    init(a / "airisk-api")
    init(a / "clientes" / "web")
    init(b / "airisk-api")                 # mismo nombre que en la primera carpeta
    init(tmp_path / "sueltos" / "aurea")   # carpeta elegida que ya es un repo
    roots = [a, b, tmp_path / "sueltos" / "aurea", a / "clientes", tmp_path / "no-existe"]
    cfg = {"git": {"repos_roots": [str(r) for r in roots]}, "projects": PROJECTS,
           "user": {"git_authors": [], "timezone": "Europe/Madrid"}}

    git = GitLocalCollector(cfg)
    repos = {r.name: r for r in git.repos()}
    assert set(repos) == {"airisk-api", "clientes/web", "otro-disco/airisk-api", "aurea"}
    assert repos["clientes/web"].root == a               # la carpeta anidada no lo duplica
    assert repos["aurea"].project == "Aurea"
    assert repos["otro-disco/airisk-api"].project == "AI Risk"
    assert any("no-existe" in e for e in git.errors)


def test_short_ref():
    assert short_ref("refs/heads/main") == "main"
    assert short_ref("refs/remotes/origin/dev") == "origin/dev"
    assert short_ref("HEAD") == "HEAD"
