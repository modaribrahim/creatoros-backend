import json

import json_repair

from app.services.openrouter import chat

PLANNER_PROMPT = """You are a search planner for a YouTube comment analytics tool.

A user asks a question about the comments of a video. You must decide:
1) whether the question can be answered EXACTLY by filtering on stored fields,
2) a clean semantic search phrase to embed for similarity retrieval.

The available fields (id, type, options) are:
<fields>

Return ONLY a JSON object, no prose:
{
  "search_text": "<a concise phrase capturing the semantic intent; empty string if the question is fully filterable>",
  "filters": [
    {"field": "<field id>", "op": "eq|gte|lte", "value": <string or number>}
  ]
}

Rules:
- Use filters ONLY for field ids and enum values listed above.
- "eq" for enums/strings/bools. "gte"/"lte" only for int/float fields.
- If the question is vague or about a topic not in the fields, leave filters
  empty and put the intent in search_text.
- If the question maps cleanly to fields (e.g. "negative comments" ->
  sentiment_label eq negative), use filters and an empty search_text.
- Provide at most 3 filters."""

ANSWER_PROMPT = """You summarize user questions about YouTube comments. Use ONLY the provided
comments and their fields. Reply concisely with concrete findings and cite
comments by their number like [1], [2]. If the comments do not answer the
question, say so. Do not invent data.

Comments:
<comments>"""


def _fields_block(fields: list[dict]) -> str:
    lines = []
    for f in fields:
        line = f"- `{f['id']}` ({f['type']})"
        if f.get("options"):
            line += ": " + ", ".join(f["options"])
        lines.append(line)
    return "\n".join(lines)


async def generate_plan(query: str, fields: list[dict]) -> dict:
    """Ask the LLM to turn a user question into a search plan."""
    prompt = PLANNER_PROMPT.replace("<fields>", _fields_block(fields))
    raw = await chat(prompt, f"Question: {query}")
    try:
        data = json_repair.loads(raw)
    except (json.JSONDecodeError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "search_text": str(data.get("search_text", "")).strip(),
        "filters": (
            data.get("filters", []) if isinstance(data.get("filters", []), list) else []
        ),
    }


def validate_filters(filters: list[dict], fields: list[dict]) -> list[dict]:
    """Keep only filters that reference real fields with valid values."""
    by_id = {f["id"]: f for f in fields}
    valid = []
    for f in filters:
        if not isinstance(f, dict):
            continue
        field_id, op = f.get("field"), f.get("op")
        schema = by_id.get(field_id) if field_id else None
        if not schema or op not in ("eq", "gte", "lte"):
            continue
        value = f.get("value")
        if value is None:
            continue
        if schema["type"] == "enum":
            options = schema.get("options") or []
            if str(value) not in options:
                continue
            value = str(value)
        elif schema["type"] in ("int", "float"):
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if op != "eq":
                valid.append({"field": field_id, "op": op, "value": value})
            continue
        valid.append({"field": field_id, "op": op, "value": value})
    return valid[:3]


def _comments_block(hits: list[dict]) -> str:
    lines = []
    for i, hit in enumerate(hits, 1):
        fields = {k: v for k, v in hit["fields"].items() if k != "index"}
        lines.append(f"{i}. {hit['text']}  |  fields: {json.dumps(fields)}")
    return "\n".join(lines)


async def generate_answer(query: str, hits: list[dict]) -> str:
    if not hits:
        return "No matching comments found."
    prompt = ANSWER_PROMPT.replace("<comments>", _comments_block(hits))
    return (await chat(prompt, f"Question: {query}")).strip()
