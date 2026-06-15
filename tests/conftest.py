"""Shared fixtures for ik test suite."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest
import requests


def make_response(
    status: int = 200,
    json_body: dict | None = None,
    text: str = "",
    chunks: list[bytes] | None = None,
) -> Mock:
    """Build a Mock requests.Response with the surface _request consumes."""
    resp = Mock(spec=requests.Response)
    resp.status_code = status
    if json_body is not None:
        resp.json.return_value = json_body
        resp.text = ""
    else:
        resp.json.side_effect = ValueError("no json")
        resp.text = text
    if chunks is not None:
        resp.iter_content.return_value = iter(chunks)
    return resp


@pytest.fixture
def drive_dict() -> dict[str, Any]:
    return {
        "id": 42,
        "name": "My Drive",
        "size": 10 * 1024**3,
        "used_size": 3 * 1024**3,
        "is_locked": False,
        "has_operation_in_progress": False,
        "created_at": "2024-01-15T10:30:00+00:00",
    }


@pytest.fixture
def file_dict() -> dict[str, Any]:
    return {
        "id": 100,
        "name": "report.pdf",
        "size": 4096,
        "type": "file",
        "parent_id": 1,
        "created_at": "2024-01-15T10:30:00+00:00",
        "modified_at": "2024-01-16T12:00:00+00:00",
        "mime": "application/pdf",
    }
