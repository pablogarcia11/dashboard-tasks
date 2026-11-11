"""Colector de git local: commits propios (incluidos los no subidos) y trabajo sin commitear.

No usa autenticación: llama a `git -C <repo>` por subprocess.
"""
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from collectors.base import Activity
from core.dates import to_work_date

SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
RS, US = "\x1e", "\x1f"  # separadores de registro y de campo en la salida de git log


@dataclass
class Repo:
    path: Path
    project: str
    common_dir: str = ""   # los worktrees de un mismo repo comparten common_dir
    is_worktree: bool = False


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
    rel = path.relative_to(root).as_posix()
    for name, entries in projects.items():
        for e in entries or []:
            if rel == e or rel.startswith(e.rstrip("/") + "/"):
                return name
    return rel.split("/")[0]


def discover_repos(root: Path, depth: int, exclude: list, projects: dict) -> list[Repo]:
    """Busca repos hasta `depth` niveles bajo root, sin entrar en los excluidos ni dentro de un repo."""
    excluded = [_norm(e) for e in exclude]
    found: list[Repo] = []

    def is_excluded(p: Path) -> bool:
        n = _norm(p)
        return any(n == e or n.startswith(e + os.sep) for e in excluded)

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


class GitLocalCollector:
    source = "git"

    def __init__(self, config: dict):
        g = config["git"]
        self.root = Path(g["repos_root"])
        self.depth = g.get("scan_depth", 3)
        self.exclude = g.get("exclude_repos", [])
        self.projects = config.get("projects", {})
        self.authors = [a.lower() for a in config["user"]["git_authors"]]
        self.tz = config["user"]["timezone"]
        self.errors: list[str] = []

    def repos(self) -> list[Repo]:
        repos = discover_repos(self.root, self.depth, self.exclude, self.projects)
        for r in repos:
            try:
                # Relativo (".git") en repos normales, absoluto en worktrees
                r.common_dir = _norm(r.path / run_git(r.path, "rev-parse", "--git-common-dir").strip())
            except RuntimeError as e:
                self.errors.append(str(e))
        return [r for r in repos if r.common_dir]

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
                extra={"repo": repo.path.relative_to(self.root).as_posix(), "branch": c["branch"],
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
        rel = repo.path.relative_to(self.root).as_posix()
        return Activity(
            source="git", kind="wip", external_id=f"wip:{rel}", ts=now.isoformat(timespec="seconds"),
            work_date=to_work_date(now, self.tz).isoformat(),
            title=f"Cambios sin commitear en {len(status)} fichero{'s' if len(status) != 1 else ''}",
            project=repo.project,
            body="\n".join(status[:30]),
            extra={"repo": rel, "branch": branch, "files": len(status),
                   "untracked": sum(1 for l in status if l.startswith("??"))},
        )
