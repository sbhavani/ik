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


@pytest.fixture
def vps_dict() -> dict[str, Any]:
    return {
        "id": 1001,
        "account_id": 5,
        "customer_name": "My VPS Cloud",
        "description": "Production environment",
        "internal_name": "vps-prod-01",
        "is_locked": False,
        "has_maintenance": False,
        "has_operation_in_progress": False,
        "is_free": False,
        "is_zero_price": False,
        "is_trial": False,
        "service_id": 200,
        "service_name": "VPS Cloud S",
        "unique_id": 1001,
        "version": 1,
        "tags": [],
        "rights": {"technical": True, "statistic": True, "check": True, "sale": True},
        "created_at": 1705314600,  # 2024-01-15 10:30:00 UTC
        "expired_at": None,
        "public_cloud": {
            "price": 12.0,
            "price_updated_at": 1705314600,
            "updated_at": 1705314600,
            "project_count": 3,
            "billing_start_at": 1705314600,
            "billing_end_at": 1736850600,
        },
    }


@pytest.fixture
def my_ksuite_dict() -> dict[str, Any]:
    return {
        "id": 1234,
        "status": "active",
        "pack_id": 7,
        "trial_expiry_at": 1736899200,  # 2025-01-15
        "pack": "kSuite Standard",
        "is_free": False,
        "drive": "9012",
        "mail": "5678",
        "has_auto_renew": "enabled",
        "can_trial": False,
        "product": "ksuite",
        "children": None,
        "data": [],
    }
