"""Parte de horas para 1million hub (ver PLAN_TECNICO.md, 7.5).

Claude solo agrupa commits en tareas, las titula y les pone categoría. Todo lo horario es determinista:
reuniones fijas, comida en el hueco sin commits más cercano a su hora, duración de cada tarea según
los huecos entre commits, tareas sin commits (de I'M BACK) en los huecos restantes, bloques de
15 min como mínimo y en múltiplos de 15 (configurable en config.yaml, `timesheet`).
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_CATEGORY = "Desarrollo de negocio"


@dataclass
class Block:
    start: int          # minutos desde medianoche
    end: int
    title: str
    project: str
    category: str
    kind: str = "task"  # task | meeting
    task_id: str = ""

    @property
    def minutes(self) -> int:
        return self.end - self.start


def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def snap(m: float, step: int) -> int:
    """Redondea al múltiplo de `step` más cercano (p. ej. cuartos de hora)."""
    return int(step * round(m / step))


def minute_of(ts: str, tz: str) -> int:
    t = datetime.fromisoformat(ts).astimezone(ZoneInfo(tz))
    return t.hour * 60 + t.minute


def place_lunch(commits: list[int], busy: list[tuple[int, int]], default: int, length: int,
                lo: int = 13 * 60, hi: int = 16 * 60, step: int = 15) -> tuple[int, int]:
    """Hueco de `length` min entre lo y hi sin commits ni reuniones, el más cercano a `default`."""
    def free(s):
        return (not any(s < c < s + length for c in commits)
                and not any(s < be and bs < s + length for bs, be in busy))
    valid = [s for s in range(lo, hi - length + 1, step) if free(s)]
    s = min(valid, key=lambda s: abs(s - default)) if valid else default
    return s, s + length


def free_intervals(start: int, end: int, busy: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out, cursor = [], start
    for bs, be in sorted(busy):
        if bs > cursor:
            out.append((cursor, min(bs, end)))
        cursor = max(cursor, be)
    if cursor < end:
        out.append((cursor, end))
    return [(s, e) for s, e in out if e > s]


def parse_tasks(text: str, commits: list[dict], categories: list[str]) -> list[dict]:
    """Valida la respuesta JSON de Claude. Cada commit acaba en exactamente una tarea."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    data = json.loads(text)
    by_sha = {c["sha"]: c for c in commits}
    seen, tasks = set(), []
    for i, t in enumerate(data.get("tareas", [])):
        shas = [s for s in t.get("commits", []) if s in by_sha and s not in seen]
        seen.update(shas)
        if t.get("commits") and not shas:
            continue  # solo traía commits inventados o repetidos
        tasks.append({
            "id": str(t.get("id") or f"t{i}"), "project": t.get("proyecto", ""),
            "title": (t.get("titulo") or "").strip() or "Por definir",
            "category": t.get("categoria") if t.get("categoria") in categories else DEFAULT_CATEGORY,
            "commits": shas, "minutes": t.get("minutos") if not shas else None,
        })
    for c in commits:  # commits que Claude no asignó: cada uno su tarea
        if c["sha"] not in seen:
            tasks.append({"id": f"c-{c['sha']}", "project": c["project"],
                          "title": f"{c['project']} - {c['subject']}", "category": DEFAULT_CATEGORY,
                          "commits": [c["sha"]], "minutes": None})
    return tasks


def build_blocks(ts_cfg: dict, meetings: list[dict], commits: list[dict], tasks: list[dict]
                 ) -> tuple[list[Block], list[str]]:
    """meetings: {start, end (min), title, project}; commits: {sha, minute}; tasks: de parse_tasks."""
    warnings = []
    step = ts_cfg.get("block_step_minutes", 15)       # duraciones en múltiplos de esto
    min_block = ts_cfg.get("min_block_minutes", 15)
    day_start, day_end = hm(ts_cfg["day_start"]), hm(ts_cfg["day_end"])
    lunch_len = hm(ts_cfg["lunch_end"]) - hm(ts_cfg["lunch_start"])
    cmins = sorted(c["minute"] for c in commits)
    if cmins:  # trabajo antes o después de la jornada habitual
        day_start = min(day_start, (cmins[0] - 15) // step * step)
        day_end = max(day_end, -(-cmins[-1] // step) * step)
    busy = []
    for m in meetings:
        if 7 * 60 <= m["start"] and m["end"] <= 21 * 60:
            day_start, day_end = min(day_start, m["start"]), max(day_end, m["end"])
        busy.append((m["start"], m["end"]))
    lunch = place_lunch(cmins, busy, hm(ts_cfg["lunch_start"]), lunch_len, step=step)
    intervals = free_intervals(day_start, day_end, busy + [lunch])

    task_of = {sha: t["id"] for t in tasks for sha in t["commits"]}
    by_id = {t["id"]: t for t in tasks}
    note_tasks = [t for t in tasks if not t["commits"]]

    # 1) Tramos de commits: cada grupo de commits seguidos de la misma tarea va desde el final
    #    del tramo anterior (o el inicio del hueco) hasta su último commit.
    pieces = []  # (start, end, task_id | None)  None = hueco sin commits
    ordered = sorted(commits, key=lambda c: c["minute"])
    for s, e in intervals:
        inside = []
        for c in ordered:
            iv = next((iv for iv in intervals if iv[0] <= c["minute"] <= iv[1]), None)
            if iv is None:  # commit en reunión o comida: cuenta en el hueco anterior
                prev = [iv for iv in intervals if iv[1] <= c["minute"]]
                iv = prev[-1] if prev else intervals[0]
            if iv == (s, e):
                inside.append((min(max(c["minute"], s), e), task_of[c["sha"]]))
        cursor = s
        for minute, tid in inside:
            if pieces and pieces[-1][2] == tid and pieces[-1][1] == cursor:
                pieces[-1] = (pieces[-1][0], minute, tid)
            else:
                pieces.append((cursor, minute, tid))
            cursor = minute
        if e > cursor:
            pieces.append((cursor, e, None))

    # 2) Huecos sin commits. Si la misma tarea sigue al otro lado (p. ej. cortada por una reunión),
    #    el hueco es de esa tarea. El resto, para las tareas de I'M BACK sin commits según su peso;
    #    si no hay, se alarga la tarea anterior (o la siguiente).
    for i, (s, e, tid) in enumerate(pieces):
        if tid is None:
            prev = next((p[2] for p in reversed(pieces[:i]) if p[2] is not None), None)
            nxt = next((p[2] for p in pieces[i + 1:] if p[2] is not None), None)
            if prev is not None and prev == nxt:
                pieces[i] = (s, e, prev)
    gaps = [p for p in pieces if p[2] is None]
    gap_total = sum(e - s for s, e, _ in gaps)
    queue = []
    if note_tasks and gap_total >= min_block:
        weights = [max(t["minutes"] or 30, min_block) for t in note_tasks]
        fit = note_tasks[: max(1, gap_total // min_block)]
        if len(fit) < len(note_tasks):
            warnings.append(f"{len(note_tasks) - len(fit)} tareas sin commits no caben en los huecos")
        total_w = sum(weights[: len(fit)])
        queue = [[t["id"], max(min_block, gap_total * w / total_w)] for t, w in zip(fit, weights)]
    filled = []
    for i, (s, e, tid) in enumerate(pieces):
        if tid is not None:
            filled.append((s, e, tid))
            continue
        cursor = s
        while queue and cursor < e:
            take = min(queue[0][1], e - cursor)
            filled.append((cursor, cursor + take, queue[0][0]))
            cursor += take
            queue[0][1] -= take
            if queue[0][1] <= 0.5:
                queue.pop(0)
        if cursor < e:
            prev = next((p[2] for p in reversed(filled) if p[2] is not None), None)
            nxt = next((p[2] for p in pieces[i + 1:] if p[2] is not None), None)
            filled.append((cursor, e, prev or nxt))

    # 3) Bloques: bordes en múltiplos de `step` (salvo los fijos de reuniones y comida),
    #    fusión de contiguos de la misma tarea, mínimo `min_block`
    fixed = {x for iv in intervals for x in iv}
    blocks: list[Block] = []
    for s, e, tid in filled:
        s = int(s) if s in fixed else snap(s, step)
        e = int(e) if e in fixed else snap(e, step)
        if e <= s:
            continue
        if tid is None:
            blocks.append(Block(s, e, "Por definir", "", DEFAULT_CATEGORY))
            continue
        t = by_id[tid]
        if blocks and blocks[-1].end == s and (blocks[-1].task_id == tid or blocks[-1].title == t["title"]):
            blocks[-1].end = e
        else:
            blocks.append(Block(s, e, t["title"], t["project"], t["category"], task_id=tid))
    merged: list[Block] = []
    for b in blocks:
        if b.minutes < min_block and merged and merged[-1].end == b.start:
            merged[-1].end = b.end
        elif merged and merged[-1].minutes < min_block and merged[-1].end == b.start:
            b.start = merged.pop().start
            merged.append(b)
        else:
            merged.append(b)
    merged = [b for b in merged if b.minutes >= min_block]
    if any(b.title == "Por definir" for b in merged):
        warnings.append("Hay huecos sin tareas: complétalos a mano")

    for m in meetings:
        merged.append(Block(m["start"], m["end"], m["title"], m["project"], "Reunión", kind="meeting"))
    merged.sort(key=lambda b: b.start)
    total = sum(b.minutes for b in merged)
    if total < ts_cfg.get("min_daily_hours", 8) * 60:
        warnings.append(f"El día suma {total // 60} h {total % 60:02d} min, menos de "
                        f"{ts_cfg.get('min_daily_hours', 8)} h")
    return merged, warnings


def parse_edited(raw: str, categories: list[str]) -> list[Block]:
    """Valida los bloques de un día editados a mano en la rejilla (JSON: [{start, end, title, project,
    category}], en minutos desde medianoche). Lanza ValueError con un mensaje para la persona.

    Cada cambio reenvía el día entero, así que aquí llegan también los bloques que la persona no ha
    tocado, tal como se calcularon: reuniones a su hora real (10:00–10:25, o de 5 min) y tareas que
    terminan donde empieza una reunión. Por eso no se redondea nada (los tramos de `block_step_minutes`
    los impone la rejilla al mover o escribir una hora) y dos reuniones pueden solaparse, como en el
    calendario. Lo demás no puede solaparse."""
    try:
        data = json.loads(raw)
    except ValueError:
        raise ValueError("No se han podido leer los cambios.")
    if not isinstance(data, list):
        raise ValueError("No se han podido leer los cambios.")
    blocks = []
    for item in data:
        try:
            start, end = round(float(item["start"])), round(float(item["end"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError("Falta el horario de una tarea.")
        title = str(item.get("title") or "").strip()[:200]
        if not title:
            raise ValueError("Escribe el nombre de la tarea.")
        if not (0 <= start < end <= 24 * 60):
            raise ValueError(f"«{title}»: la hora de fin tiene que ser posterior a la de inicio.")
        category = item.get("category") if item.get("category") in categories else DEFAULT_CATEGORY
        blocks.append(Block(start, end, title, str(item.get("project") or "").strip()[:80], category,
                            kind="meeting" if category == "Reunión" else "task"))
    blocks.sort(key=lambda b: (b.start, b.end))
    for i, b in enumerate(blocks):
        for prev in blocks[:i]:
            if b.start < prev.end and not (b.kind == prev.kind == "meeting"):
                raise ValueError(f"«{b.title}» se solapa con «{prev.title}».")
    return blocks


def edited_json(blocks: list[Block]) -> str:
    return json.dumps([{"start": b.start, "end": b.end, "title": b.title, "project": b.project,
                        "category": b.category} for b in blocks], ensure_ascii=False)


def short_day_warning(blocks: list[Block], ts_cfg: dict) -> list[str]:
    total, minimum = sum(b.minutes for b in blocks), ts_cfg.get("min_daily_hours", 8)
    if total < minimum * 60:
        return [f"El día suma {total // 60} h {total % 60:02d} min, menos de {minimum} h"]
    return []


def as_text(blocks: list[Block]) -> str:
    return "\n".join(f"{fmt(b.start)}–{fmt(b.end)}  {b.title}  ({b.category})" for b in blocks)
