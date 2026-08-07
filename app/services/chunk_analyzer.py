import asyncio
import json
import re
from pathlib import Path

import json_repair

from app.core.config import settings
from app.services.openrouter import chat

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "comment_chunk_analyzer.md"
)


def build_system_prompt(fields: list[dict]) -> str:
    lines = []
    for f in fields:
        line = f"- `{f['id']}` ({f['type']})"
        if f.get("options"):
            line += ": " + ", ".join(f["options"])
        lines.append(line)
    return SKILL_PATH.read_text().replace("<vocab>", "\n".join(lines))


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


INT_RANGES = {"priority": (0, 4), "urgency": (0, 3)}


def _coerce(value, expected: str):
    if value is None:
        return value
    if expected == "float":
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None
    if expected == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if expected == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)
    if expected in ("string_list",):
        if isinstance(value, list):
            return [str(v) for v in value[:5]]
        return []
    return value  # enum / string pass-through


def _default_value(ftype: str):
    if ftype == "float":
        return None
    if ftype == "int":
        return 0
    if ftype == "bool":
        return False
    if ftype == "string_list":
        return []
    return None


def _coerce_enum(value, options: list[str]):
    if value is None:
        return "other" if options else None
    s = str(value)
    if options and s not in options:
        return "other"
    return s


def _clamp_int(value: int, field_id: str) -> int:
    if field_id in INT_RANGES:
        lo, hi = INT_RANGES[field_id]
        return max(lo, min(hi, value))
    return value


def _normalize_record(raw: dict, fields: list[dict], index: int) -> dict:
    out = {"index": index}
    for f in fields:
        fid, ftype, options = f["id"], f["type"], f.get("options", [])
        value = raw.get(fid)
        if value is None:
            out[fid] = _default_value(ftype)
            continue
        if ftype == "enum":
            out[fid] = _coerce_enum(value, options)
        elif ftype == "int":
            out[fid] = _clamp_int(_coerce(value, ftype), fid)
        else:
            out[fid] = _coerce(value, ftype)
    return out


async def analyze_chunk(
    items: list[tuple[str, str]], system_prompt: str, fields: list[dict]
) -> list[dict]:
    if not items:
        return []
    payload = "\n".join(f"{i+1}. {text}" for i, (_, text) in enumerate(items))
    raw = await chat(system_prompt, f"Comments ({len(items)}):\n{payload}")
    try:
        data = json_repair.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        return []
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        return []
    out = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            continue
        record = _normalize_record(r, fields, i + 1)
        record["comment_id"] = items[i][0]
        out.append(record)
    return out


async def analyze_comments(
    items: list[tuple[str, str]], fields: list[dict]
) -> tuple[list[dict], list[str]]:
    system_prompt = build_system_prompt(fields)
    chunks = [
        items[i : i + settings.chunk_size]
        for i in range(0, len(items), settings.chunk_size)
    ]

    sem = asyncio.Semaphore(settings.max_concurrency)

    async def run(chunk: list[tuple[str, str]]) -> list[dict]:
        async with sem:
            return await analyze_chunk(chunk, system_prompt, fields)

    results = await asyncio.gather(*(run(c) for c in chunks))
    records = [r for result in results for r in result]

    return records, [f["id"] for f in fields]
