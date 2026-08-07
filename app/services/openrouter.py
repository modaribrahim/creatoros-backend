from openai import AsyncOpenAI

from app.core.config import settings

_embed_client = None
_chat_client = None


def get_embed_client() -> AsyncOpenAI:
    global _embed_client
    if _embed_client is None:
        _embed_client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
    return _embed_client


def get_chat_client() -> AsyncOpenAI:
    global _chat_client
    if _chat_client is None:
        _chat_client = AsyncOpenAI(
            api_key=settings.analyze_api_key,
            base_url=settings.analyze_base_url,
        )
    return _chat_client


async def embed(texts: list[str]) -> list[list[float]]:
    response = await get_embed_client().embeddings.create(
        model=settings.embed_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def chat(system: str, user: str) -> str:
    response = await get_chat_client().chat.completions.create(
        model=settings.analyze_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        timeout=300,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or ""


async def chat_message(
    messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.3
):
    """Send a conversation to the chat LLM, optionally with tool/function calling.

    Returns the raw message object so callers can inspect `tool_calls`.
    If the provider rejects the `tools` parameter, retries without it so chat
    degrades gracefully to plain Q&A.
    """
    kwargs: dict = {
        "model": settings.analyze_model,
        "messages": messages,
        "temperature": temperature,
        "timeout": 300,
    }
    try:
        if tools:
            kwargs["tools"] = tools
        response = await get_chat_client().chat.completions.create(**kwargs)
        return response.choices[0].message
    except Exception:
        if not tools:
            raise
        kwargs.pop("tools", None)
        response = await get_chat_client().chat.completions.create(**kwargs)
        return response.choices[0].message
