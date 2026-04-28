from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

import litellm
from pydantic import BaseModel

from drift_bench.models import Usage

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _extract_usage(response) -> Usage:
    u = response.usage
    if u is None:
        return Usage()
    return Usage(
        prompt_tokens=u.prompt_tokens or 0,
        completion_tokens=u.completion_tokens or 0,
        total_tokens=u.total_tokens or 0,
    )


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _strictify_json_schema(schema):
    """Make Pydantic JSON schema acceptable to strict OpenAI-compatible providers."""
    if isinstance(schema, dict):
        if schema.get("type") == "object" or "properties" in schema:
            schema.setdefault("additionalProperties", False)
        for value in schema.values():
            _strictify_json_schema(value)
    elif isinstance(schema, list):
        for item in schema:
            _strictify_json_schema(item)
    return schema


async def complete(
    model: str,
    messages: list[dict],
    temperature: float | None = None,
    max_tokens: int = 1024,
) -> tuple[str, Usage]:
    kwargs = dict(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        num_retries=3,
        timeout=120,
    )
    if temperature is not None:
        kwargs["temperature"] = temperature

    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content or ""
    return content, _extract_usage(response)


async def complete_json(
    model: str,
    messages: list[dict],
    response_model: type[T],
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> tuple[T, Usage]:
    schema = _strictify_json_schema(response_model.model_json_schema())

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        num_retries=3,
        timeout=120,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__,
                "schema": schema,
                "strict": True,
            },
        },
    )

    raw = response.choices[0].message.content or "{}"
    raw = _strip_fences(raw)
    usage = _extract_usage(response)

    try:
        parsed = response_model.model_validate_json(raw)
    except Exception:
        # Fallback: some models don't respect json_schema but do output JSON
        logger.warning("Strict JSON parse failed, attempting lenient parse")
        try:
            data = json.loads(raw)
            parsed = response_model.model_validate(data)
        except Exception:
            logger.error("JSON parse failed. Raw response: %s", raw[:500])
            raise

    return parsed, usage
