"""Helpers for exporting the FastAPI OpenAPI schema."""

from __future__ import annotations

import json
from pathlib import Path

from phag.api import app


def export_openapi_spec(output_path: Path) -> None:
    """Write the current OpenAPI schema to a JSON file."""
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
