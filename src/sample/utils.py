from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

RE_TAG_RESPONSE = re.compile(r"<response>(.*?)</response>", flags=re.DOTALL | re.IGNORECASE)
RE_TAG_SKILL = re.compile(r"<skill>.*?</skill>", flags=re.S | re.IGNORECASE)
RE_JSON_CODE_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", flags=re.S)
RE_JSON_BRACE = re.compile(r"(\{.*\})", flags=re.S)


def extract_tag_content(text: str, tag: str = "response") -> Optional[str]:
    if not text:
        return None
    if tag == "response":
        match = RE_TAG_RESPONSE.search(text)
    else:
        match = re.search(rf"<{tag}>(.*?)</{tag}>", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else text.strip()


def remove_tags(text: str, tag: str = "response") -> str:
    if not text:
        return ""
    if tag == "skill":
        return RE_TAG_SKILL.sub("", text).strip()
    return re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.S | re.IGNORECASE).strip()


def safe_json_loads(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("empty text for JSON parse")

    content = extract_tag_content(text, tag="response") or ""
    candidate = _strip_code_fence(content)

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = RE_JSON_CODE_BLOCK.search(content) or RE_JSON_BRACE.search(content)
    if match:
        blob = _strip_code_fence(match.group(1))
        parsed = json.loads(blob)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("JSON parse failed: no valid JSON object found")


def format_transcript(transcript: List[Dict[str, Any]], *, for_profile: bool = False) -> str:
    lines: List[str] = []
    for msg in transcript:
        role = msg.get("role")
        content = str(msg.get("content") or "")
        if role == "system" or not content.strip():
            continue

        if for_profile:
            content = extract_tag_content(content, tag="response") or ""
        else:
            content = remove_tags(content, tag="skill")

        content = content.replace("\n", " ").strip()
        if not content:
            continue

        speaker = "counsel" if role == "assistant" else "client"
        lines.append(f"{speaker}：{content}")

    return "\n".join(lines)


def strip_end_token(text: str, end_token: str) -> tuple[str, bool]:
    cleaned = (text or "").strip()
    if not end_token:
        return cleaned, False
    if cleaned.endswith(end_token):
        return cleaned[: -len(end_token)].strip(), True
    return cleaned, False


def _strip_code_fence(text: str) -> str:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
    if raw.endswith("```"):
        raw = re.sub(r"```$", "", raw).strip()
    return raw
