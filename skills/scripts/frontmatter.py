"""Frontmatter parser — stdlib-only subset for doc-kit documents.

Replaces PyYAML for the small YAML subset used by doc-kit frontmatter:
scalar values, empty values, inline comments, flat lists, list-of-dicts
(e.g. ``depends_on`` / ``superseded_by``).

Mirrors the parse()/dump() API of the original PyYAML-based implementation.
"""
from __future__ import annotations

import re
from typing import Any


class FrontmatterParseError(Exception):
    """Raised when frontmatter parsing fails."""


def _strip_inline_comment(line: str) -> str:
    """Strip a trailing '# comment' (a # preceded by whitespace), ignoring quoted parts."""
    in_quote: str | None = None
    for i, ch in enumerate(line):
        if in_quote:
            if ch == in_quote:
                in_quote = None
        elif ch in "\"'":
            in_quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line


def _parse_value(raw: str) -> Any:
    v = raw.strip()
    if v == "":
        return None
    if v == "[]":
        return []
    if v == "true":
        return True
    if v == "false":
        return False
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        return v[1:-1]
    return v


def _parse_yaml_block(text: str) -> dict:
    meta: dict = {}
    last_key: str | None = None
    pending_dict: dict | None = None  # 当前 list-of-dicts 中正在构建的项
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        stripped = _strip_inline_comment(line)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip())
        content = stripped.strip()
        if content.startswith("- "):
            # List item (indented under a key, e.g. "  - doc: x")
            item_text = content[2:].strip()
            if last_key is None:
                continue  # top-level list without key — not used in doc-kit
            if meta.get(last_key) is None:
                meta[last_key] = []
            if ":" in item_text:
                k, v = item_text.split(":", 1)
                d = {k.strip(): _parse_value(v)}
                meta[last_key].append(d)
                pending_dict = d
            else:
                meta[last_key].append(_parse_value(item_text))
                pending_dict = None
        elif ":" in content and indent > 0 and pending_dict is not None:
            # Continuation line of a dict item inside a list-of-dicts
            k, v = content.split(":", 1)
            pending_dict[k.strip()] = _parse_value(v)
        elif ":" in content:
            k, v = content.split(":", 1)
            last_key = k.strip()
            meta[last_key] = _parse_value(v)
            pending_dict = None
    return meta


def parse(text: str) -> tuple[dict, str]:
    """Parse frontmatter from Markdown text.

    Returns (meta_dict, body_string).
    Only the first --- pair is treated as frontmatter.
    """
    pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(pattern, text, re.DOTALL)
    if not match:
        raise FrontmatterParseError("No valid frontmatter found (must start with ---)")

    yaml_text = match.group(1)
    body = text[match.end():]
    meta = _parse_yaml_block(yaml_text)
    if not isinstance(meta, dict):
        raise FrontmatterParseError("Frontmatter must be a YAML mapping (dictionary)")
    return meta, body


def _dump_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    # Quote when needed to stay parseable by our own parser.
    if (
        ":" in s
        or "#" in s
        or s.startswith("-")
        or s.strip() != s
        or (s and s[0] in "\"'")
    ):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def dump(meta: dict, body: str) -> str:
    """Assemble meta dict + body back into a full Markdown file."""
    lines: list[str] = []
    for key, value in meta.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    if isinstance(item, dict):
                        first = True
                        for ik, iv in item.items():
                            if first:
                                lines.append(f"  - {ik}: {_dump_value(iv)}")
                                first = False
                            else:
                                lines.append(f"    {ik}: {_dump_value(iv)}")
                    else:
                        lines.append(f"  - {_dump_value(item)}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for ik, iv in value.items():
                lines.append(f"  {ik}: {_dump_value(iv)}")
        else:
            v = _dump_value(value)
            lines.append(f"{key}: {v}" if v else f"{key}:")
    yaml_text = "\n".join(lines)
    return f"---\n{yaml_text}\n---\n\n{body}"


class FrontmatterParser:
    """Parse and write YAML frontmatter from/to Markdown files（类 API）。

    包装模块级 parse() / dump()，与原有 FrontmatterParser 类接口保持一致。
    """

    @staticmethod
    def parse(text: str) -> tuple[dict, str]:
        """Parse frontmatter from Markdown text. Returns (meta_dict, body_string)."""
        return parse(text)

    @staticmethod
    def dump(meta: dict, body: str) -> str:
        """Assemble meta dict + body back into a full Markdown file."""
        return dump(meta, body)
