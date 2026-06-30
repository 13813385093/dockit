"""Frontmatter parser for MCP tools — minimal version extracted from app/engine.

Only includes parse() and dump(), which is all mcp_server.py uses.
"""
import re

import yaml


class FrontmatterParseError(Exception):
    """Raised when frontmatter parsing fails."""


class FrontmatterParser:
    """Parse and write YAML frontmatter from/to Markdown files."""

    @staticmethod
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
        try:
            meta = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise FrontmatterParseError(f"Invalid YAML in frontmatter: {e}")

        if not isinstance(meta, dict):
            raise FrontmatterParseError("Frontmatter must be a YAML mapping (dictionary)")

        return meta, body

    @staticmethod
    def dump(meta: dict, body: str) -> str:
        """Assemble meta dict + body back into a full Markdown file."""
        yaml_text = yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{yaml_text}\n---\n\n{body}"
