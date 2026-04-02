"""Shared configuration loading helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover - fallback path for minimal environments
    yaml = None  # type: ignore[assignment]


def load_yaml_mapping(path: str | Path) -> Dict[str, Any]:
    """Load a YAML file and ensure the root object is a mapping."""
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    data: Any
    if yaml is not None:
        data = yaml.safe_load(text)
    else:
        data = _simple_yaml_parse(text)

    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping: {config_path}")
    return data


def _simple_yaml_parse(text: str) -> Any:
    """Parse a small YAML subset used by project configs."""
    lines = _preprocess_lines(text)
    if not lines:
        return {}
    parsed, next_index = _parse_block(lines, 0, lines[0][0])
    if next_index != len(lines):
        raise ValueError("invalid YAML structure near end of file")
    return parsed


def _preprocess_lines(text: str) -> List[Tuple[int, str]]:
    output: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        stripped = raw.lstrip(" ")
        if stripped.startswith("#"):
            continue
        indent = len(raw) - len(stripped)
        line = _strip_comment(stripped).rstrip()
        if line:
            output.append((indent, line))
    return output


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def _parse_block(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[Any, int]:
    if start >= len(lines):
        return {}, start

    current_indent, current_text = lines[start]
    if current_indent != indent:
        raise ValueError(f"unexpected indentation at line index {start}")

    if current_text.startswith("- "):
        return _parse_list(lines, start, indent)
    return _parse_mapping(lines, start, indent)


def _parse_mapping(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[Dict[str, Any], int]:
    result: Dict[str, Any] = {}
    idx = start
    while idx < len(lines):
        cur_indent, text = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise ValueError(f"unexpected indentation in mapping at line index {idx}")
        if text.startswith("- "):
            raise ValueError(f"unexpected list item in mapping at line index {idx}")

        match = re.match(r"^([^:]+):(.*)$", text)
        if not match:
            raise ValueError(f"invalid mapping entry at line index {idx}: {text!r}")
        key = match.group(1).strip()
        rest = match.group(2).strip()

        if rest:
            result[key] = _parse_scalar(rest)
            idx += 1
            continue

        idx += 1
        if idx >= len(lines) or lines[idx][0] <= indent:
            result[key] = {}
            continue
        nested_indent = lines[idx][0]
        value, idx = _parse_block(lines, idx, nested_indent)
        result[key] = value

    return result, idx


def _parse_list(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[List[Any], int]:
    result: List[Any] = []
    idx = start
    while idx < len(lines):
        cur_indent, text = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise ValueError(f"unexpected indentation in list at line index {idx}")
        if not text.startswith("- "):
            break

        rest = text[2:].strip()
        idx += 1
        if rest:
            result.append(_parse_scalar(rest))
            continue

        if idx >= len(lines) or lines[idx][0] <= indent:
            result.append(None)
            continue

        nested_indent = lines[idx][0]
        value, idx = _parse_block(lines, idx, nested_indent)
        result.append(value)
    return result, idx


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    lower = text.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "none"}:
        return None

    if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
        return text[1:-1]

    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    if re.fullmatch(r"[-+]?\d+\.\d+", text):
        return float(text)

    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]

    return text
