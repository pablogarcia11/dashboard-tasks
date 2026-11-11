"""Colector de git local: commits propios (incluidos los no subidos) y trabajo sin commitear.

No usa autenticación: llama a `git -C <repo>` por subprocess.
"""
import fnmatch
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from collectors.base import Activity
from core.config import ROOT
from core.dates import to_work_date

SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
RS, US = "\x1e", "\x1f"  # separadores de registro y de campo en la salida de git log


@dataclass
class Repo:
    path: Path
    project: str
    common_dir: str = ""   # los worktrees de un mismo repo comparten common_dir
    is_worktree: bool = False
    name: str = ""         # ruta relativa a su carpeta: la clave en Ajustes y en la actividad guardada
    root: Path | None = None


def run_git(path: Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-c", "core.quotepath=off", "-C", str(path), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} en {path}: {p.stderr.strip()}")
    return p.stdout


def git_marker(path: Path) -> str | None:
    """'dir' si es un repo normal, 'file' si es un worktree, None si no es repo."""
    g = path / ".git"
    if g.is_dir():
        return "dir" if (g / "HEAD").is_file() else None  # .git vacío (p. ej. aurea) no cuenta
    if g.is_file():
        return "file" if g.read_text(encoding="utf-8", errors="replace").startswith("gitdir:") else None
    return None


def _norm(p: Path | str) -> str:
    return os.path.normcase(os.path.abspath(p))


def project_for(path: Path, root: Path, projects: dict) -> str:
    """Proyecto de un repo según la nomenclatura de la empresa (config.yaml, `projects`).

    Cada patrón (admite comodines: `airisk*`) se compara con el nombre del repo y luego con el de cada
    carpeta que lo contiene, de dentro afuera; así no depende de dónde tenga cada uno sus repos.
    Sin coincidencia: el nombre de la carpeta de primer nivel.
    """
    parts = path.relative_to(root).parts
    for component in reversed(parts):
        for name, patterns in projects.items():
            if any(fnmatch.fnmatch(component.lower(), p.lower()) for p in patterns or []):
                return name
    return parts[0]


def repos_base(root: Path) -> Path:
    """Carpeta respecto a la que se nombran los repos de root (su padre si root ya es un repo)."""
    return root.parent if git_marker(root) else root


def discover_repos(root: Path, depth: int, exclude: list, projects: dict) -> list[Repo]:
    """Busca repos hasta `depth` niveles bajo root, sin entrar en los excluidos ni dentro de un repo.

    Si root es ya un repo (alguien que elige sus repos uno a uno), es el único.
    """
    excluded = [_norm(e) for e in exclude]
    found: list[Repo] = []

    def is_excluded(p: Path) -> bool:
        n = _norm(p)
        return any(n == e or n.startswith(e + os.sep) for e in excluded)

    marker = git_marker(root)
    if marker:
        return [] if is_excluded(root) else [Repo(root, project_for(root, root.parent, projects),
                                                  is_worktree=marker == "file")]

    def walk(d: Path, level: int):
        try:
            children = sorted(c for c in d.iterdir() if c.is_dir())
        except OSError:
            return
        for c in children:
            if c.name.startswith(".") or c.name in SKIP_DIRS or is_excluded(c):
                continue
            marker = git_marker(c)
            if marker:
                found.append(Repo(c, project_for(c, root, projects), is_worktree=marker == "file"))
            elif level < depth:
                walk(c, level + 1)

    walk(root, 1)
    return found


def parse_log(output: str) -> list[dict]:
    """Parsea `git log --format=<RS>%H<US>%an<US>%ae<US>%aI<US>%S<US>%s --shortstat`.

    El asunto va el último para que un carácter raro en él no descuadre los campos.
    """
    commits = []
    for chunk in output.split(RS):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        header, _, rest = chunk.partition("\n")
        sha, name, email, date, source, subject = header.split(US, 5)
        stat = {"files": 0, "insertions": 0, "deletions": 0}
        for part in rest.strip().split(","):
            part = part.strip()
            if not part:
                continue
            n = int(part.split()[0])
            if "file" in part:
                stat["files"] = n
            elif "insertion" in part:
                stat["insertions"] = n
            elif "deletion" in part:
                stat["deletions"] = n
        commits.append({"sha": sha, "author": name, "email": email, "date": date,
                        "subject": subject, "branch": short_ref(source), **stat})
    return commits


def short_ref(ref: str) -> str:
    for prefix in ("refs/heads/", "refs/remotes/", "refs/"):
        if ref.startswith(prefix):
            return ref[len(prefix):]
    return ref


def git_email(path: Path | None = None) -> str | None:
    """user.email de git: el global (path=None) o el efectivo de un repo (el suyo o, si no tiene, el global)."""
    args = ["config", "--global", "user.email"] if path is None else ["-C", str(path), "config", "user.email"]
    try:
        p = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip().lower() or None


def detect_author_emails(repos: list["Repo"]) -> set[str]:
    """Emails con los que la persona firma sus commits: el global y el configurado en cada repo."""
    emails = {git_email()}
    emails.update(git_email(r.path) for r in repos)
    return {e for e in emails if e}


class GitLocalCollector:
    source = "git"

    def __init__(self, config: dict):
        g = config["git"]
        # Carpetas elegidas en Ajustes (antes había una sola: repos_root)
        roots = g.get("repos_roots") or ([g["repos_root"]] if g.get("repos_root") else [])
        self.roots = [Path(r) for r in roots]
        self.depth = g.get("scan_depth", 3)
        # El propio dashboard nunca se recoge (no es trabajo de empresa); el resto se controla en Ajustes
        self.exclude = (g.get("exclude_repos") or []) + [str(ROOT)]
        self.projects = config.get("projects", {})
        # Emails añadidos a mano en Ajustes; los detectados en git se suman al descubrir los repos
        self.manual_authors = {a.lower() for a in config["user"].get("git_authors") or []}
        self.detected_authors: set[str] = set()
        self.authors = set(self.manual_authors)
        self.tz = config["user"]["timezone"]
        self.errors: list[str] = []

    def repos(self) -> list[Repo]:
        if not self.roots:
            self.errors.append("No hay carpeta de repositorios: elígela en Ajustes")
            return []
        repos, seen, names = [], set(), set()
        for root in self.roots:
            if not root.is_dir():
                self.errors.append(f"No se encuentra la carpeta {root}: quítala o cámbiala en Ajustes")
                continue
            base = repos_base(root)
            for r in discover_repos(root, self.depth, self.exclude, self.projects):
                if _norm(r.path) in seen:   # carpetas elegidas una dentro de otra
                    continue
                seen.add(_norm(r.path))
                r.root, r.name = root, r.path.relative_to(base).as_posix()
                if r.name in names:         # mismo nombre en dos carpetas: se distingue por la carpeta
                    r.name = f"{base.name}/{r.name}"
                names.add(r.name)
                repos.append(r)
        for r in repos:
            try:
                # Relativo (".git") en repos normales, absoluto en worktrees
                r.common_dir = _norm(r.path / run_git(r.path, "rev-parse", "--git-common-dir").strip())
            except RuntimeError as e:
                self.errors.append(str(e))
        repos = [r for r in repos if r.common_dir]
        # Un worktree es el mismo repo: hereda el proyecto del repo principal
        mains = {r.common_dir: r.project for r in repos if not r.is_worktree}
        for r in repos:
            if r.is_worktree and r.common_dir in mains:
                r.project = mains[r.common_dir]
        self.detected_authors = detect_author_emails(repos)
        self.authors = self.manual_authors | self.detected_authors
        return repos

    def collect(self, since: datetime, until: datetime, include_wip: bool = False) -> list[Activity]:
        repos = self.repos()
        groups: dict[str, list[Repo]] = {}
        for r in repos:
            groups.setdefault(r.common_dir, []).append(r)

        items: list[Activity] = []
        for members in groups.values():
            # El repo principal (no worktree) da nombre al grupo
            main = next((m for m in members if not m.is_worktree), members[0])
            try:
                items += self._commits(main, since, until)
            except RuntimeError as e:
                self.errors.append(str(e))
            if include_wip:
                for m in members:
                    try:
                        wip = self._wip(m)
                        if wip:
                            items.append(wip)
                    except RuntimeError as e:
                        self.errors.append(str(e))
        return items

    def _commits(self, repo: Repo, since: datetime, until: datetime) -> list[Activity]:
        # --since filtra por fecha de commit (>= fecha de autor); afinamos por fecha de autor después
        args = ["log", "--all", "--no-merges", f"--since={since.isoformat()}",
                f"--format={RS}%H{US}%an{US}%ae{US}%aI{US}%S{US}%s", "--shortstat"]
        args += [f"--author={a}" for a in self.authors]
        commits = parse_log(run_git(repo.path, *args))
        if not commits:
            return []
        unpushed = set(run_git(repo.path, "rev-list", "--all", "--not", "--remotes").split())
        has_remote = bool(run_git(repo.path, "remote").strip())

        out, seen = [], set()
        for c in commits:
            ts = datetime.fromisoformat(c["date"])
            if c["sha"] in seen or c["email"].lower() not in self.authors or not (since <= ts < until):
                continue
            seen.add(c["sha"])
            out.append(Activity(
                source="git", kind="commit", external_id=c["sha"], ts=c["date"],
                work_date=to_work_date(ts, self.tz).isoformat(), title=c["subject"],
                project=repo.project,
                extra={"repo": repo.name, "branch": c["branch"],
                       "sha": c["sha"][:8], "pushed": has_remote and c["sha"] not in unpushed,
                       "files": c["files"], "insertions": c["insertions"], "deletions": c["deletions"]},
            ))
        return out

    def _wip(self, repo: Repo) -> Activity | None:
        status = [l for l in run_git(repo.path, "status", "--porcelain").splitlines() if l.strip()]
        if not status:
            return None
        branch = run_git(repo.path, "branch", "--show-current").strip() or "(HEAD separado)"
        now = datetime.now().astimezone()
        rel = repo.name
        return Activity(
            source="git", kind="wip", external_id=f"wip:{rel}", ts=now.isoformat(timespec="seconds"),
            work_date=to_work_date(now, self.tz).isoformat(),
            title=f"Cambios sin commitear en {len(status)} fichero{'s' if len(status) != 1 else ''}",
            project=repo.project,
            body="\n".join(status[:30]),
            extra={"repo": rel, "branch": branch, "files": len(status),
                   "untracked": sum(1 for l in status if l.startswith("??"))},
        )
