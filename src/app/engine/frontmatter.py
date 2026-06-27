"""Frontmatter parser - parse and write YAML frontmatter in Markdown files."""
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml


class FrontmatterParseError(Exception):
    """Raised when frontmatter parsing fails."""


class FrontmatterValidationError(Exception):
    """Raised when frontmatter validation fails."""


REQUIRED_FIELDS_BY_LEVEL = {
    "top": ["doc_type", "level", "version"],
    "module": ["doc_type", "module", "level", "version"],
    "feature": ["doc_type", "module", "feature", "level", "version"],
}


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

    @staticmethod
    def validate(meta: dict) -> list[str]:
        """Validate frontmatter fields. Returns list of error messages (empty = valid)."""
        errors: list[str] = []

        # Validate doc_type
        doc_type = meta.get("doc_type")
        if not doc_type:
            errors.append("Missing required field: doc_type")
        elif not isinstance(doc_type, str):
            errors.append("doc_type must be a string")

        # Validate version format
        version = meta.get("version", "")
        if version:
            if not re.match(r"^\d+\.\d+\.\d+$", str(version)):
                errors.append(f"Invalid version format: '{version}' (must be major.minor.patch)")

        # Validate level
        level = meta.get("level")
        valid_levels = {"top", "module", "feature"}
        if level and level not in valid_levels:
            errors.append(f"Invalid level: '{level}' (must be one of: {', '.join(sorted(valid_levels))})")

        # Validate level-specific required fields
        if level in REQUIRED_FIELDS_BY_LEVEL:
            for field in REQUIRED_FIELDS_BY_LEVEL[level]:
                if field not in meta or meta[field] is None:
                    errors.append(f"Missing required field for level '{level}': {field}")

        # Validate status if present
        status = meta.get("status")
        valid_statuses = {"active", "deprecated", "archived", "invalid"}
        if status and status not in valid_statuses:
            errors.append(f"Invalid status: '{status}' (must be one of: {', '.join(sorted(valid_statuses))})")

        # Validate depends_on version format
        depends_on = meta.get("depends_on", [])
        if isinstance(depends_on, list):
            for i, dep in enumerate(depends_on):
                if isinstance(dep, dict):
                    dep_version = dep.get("version", "")
                    if dep_version and not re.match(r"^\d+\.\d+\.\d+$", str(dep_version)):
                        errors.append(f"depends_on[{i}].version: '{dep_version}' must be exact semver (no ranges)")
                    if "doc" not in dep:
                        errors.append(f"depends_on[{i}]: missing required field 'doc'")
                    if "module" not in dep:
                        errors.append(f"depends_on[{i}]: missing required field 'module'")

        return errors

    @staticmethod
    def now_iso() -> str:
        """Return current UTC time as ISO 8601 string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    @staticmethod
    def read_file(path: Path) -> tuple[dict, str]:
        """Read a file from disk and parse its frontmatter."""
        text = path.read_text(encoding="utf-8")
        return FrontmatterParser.parse(text)

    @staticmethod
    def write_file(path: Path, meta: dict, body: str):
        """Write meta + body to a file on disk."""
        text = FrontmatterParser.dump(meta, body)
        path.write_text(text, encoding="utf-8")
