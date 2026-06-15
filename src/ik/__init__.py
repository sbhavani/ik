"""Infomaniak kDrive API client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator

import requests


API_BASE = "https://api.infomaniak.com"


@dataclass
class Drive:
    """Represents a kDrive."""

    id: int
    name: str
    size: int
    used_size: int
    is_locked: bool
    has_operation_in_progress: bool
    created_at: datetime | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Drive:
        return cls(
            id=data.get("id", 0),
            name=data.get("name", "Unnamed"),
            size=data.get("size", 0),
            used_size=data.get("used_size", 0),
            is_locked=data.get("is_locked", False),
            has_operation_in_progress=data.get("has_operation_in_progress", False),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
        )


@dataclass
class File:
    """Represents a file or directory in kDrive."""

    id: int
    name: str
    size: int
    is_directory: bool
    parent_id: int | None
    created_at: datetime | None
    modified_at: datetime | None
    mime_type: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> File:
        return cls(
            id=data.get("id", 0),
            name=data.get("name", "?"),
            size=data.get("size", 0),
            is_directory=data.get("type") == "dir",
            parent_id=data.get("parent_id"),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
            modified_at=datetime.fromisoformat(data["modified_at"])
            if data.get("modified_at")
            else None,
            mime_type=data.get("mime"),
        )


@dataclass
class MoveOperation:
    """Handle to an async kDrive move/rename operation.

    The kDrive move endpoint returns a CancelResource (UUID + valid_until)
    rather than the moved file. The operation runs in the background; the
    cancel_id can be polled via /1/async/tasks/{id} or canceled via
    /2/drive/{drive_id}/cancel.
    """

    cancel_id: str
    valid_until: datetime | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> MoveOperation:
        valid = data.get("valid_until")
        return cls(
            cancel_id=data.get("cancel_id", ""),
            valid_until=datetime.fromtimestamp(valid) if valid else None,
        )


class KDriveClient:
    """HTTP client for the Infomaniak kDrive API."""

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )
        self._account_id: int | None = None

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
        data: bytes | None = None,
        stream: bool = False,
    ) -> dict | requests.Response:
        url = f"{API_BASE}{path}"
        resp = self.session.request(
            method, url, params=params, json=json_body, data=data, stream=stream
        )
        if stream:
            return resp

        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}

        if resp.status_code >= 400:
            err = body.get("error", {})
            code = err.get("code", resp.status_code)
            desc = err.get("description", resp.text[:200])
            raise KDriveError(f"API Error ({code}): {desc}")

        return body

    @property
    def account_id(self) -> int:
        """Fetch and cache the Infomaniak account ID."""
        if self._account_id is None:
            body = self._request("GET", "/1/accounts")
            accounts = body.get("data", [])
            if not accounts:
                raise KDriveError("No Infomaniak accounts found.")
            self._account_id = accounts[0]["id"]
        return self._account_id

    # ── Drive Operations ────────────────────────────────────────────────

    def list_drives(self) -> list[Drive]:
        """List all kDrives for the account."""
        body = self._request("GET", "/2/drive", params={"account_id": self.account_id})
        return [Drive.from_api(d) for d in body.get("data", [])]

    def get_drive(self, drive_id: int) -> Drive:
        """Get details of a specific drive."""
        body = self._request("GET", f"/2/drive/{drive_id}")
        return Drive.from_api(body.get("data", {}))

    # ── File Operations ────────────────────────────────────────────────

    def list_files(
        self,
        drive_id: int,
        directory_id: int = 1,
        order_by: str = "name",
        order_dir: str = "asc",
    ) -> Iterator[File]:
        """List files in a directory, automatically handling pagination."""
        cursor = None
        while True:
            params = {"order_by": order_by, "order_direction": order_dir}
            if cursor:
                params["cursor"] = cursor

            body = self._request(
                "GET", f"/3/drive/{drive_id}/files/{directory_id}/files", params=params
            )
            files = body.get("data", [])
            for f in files:
                yield File.from_api(f)

            if not body.get("has_more", False):
                break
            cursor = body.get("cursor")

    def get_file(self, drive_id: int, file_id: int) -> File:
        """Get metadata for a specific file or directory."""
        body = self._request("GET", f"/3/drive/{drive_id}/files/{file_id}")
        return File.from_api(body.get("data", {}))

    def create_directory(self, drive_id: int, parent_id: int, name: str) -> File:
        """Create a new directory."""
        body = self._request(
            "POST",
            f"/3/drive/{drive_id}/files/{parent_id}/directory",
            json_body={"name": name},
        )
        return File.from_api(body.get("data", {}))

    def upload_file(
        self,
        drive_id: int,
        directory_id: int,
        file_name: str,
        file_data: bytes,
        conflict: str = "rename",
    ) -> File:
        """Upload a file to a directory."""
        body = self._request(
            "POST",
            f"/3/drive/{drive_id}/upload",
            params={
                "directory_id": directory_id,
                "file_name": file_name,
                "total_size": len(file_data),
                "conflict": conflict,
            },
            data=file_data,
        )
        return File.from_api(body.get("data", {}))

    def download_file(self, drive_id: int, file_id: int) -> requests.Response:
        """Download a file (returns streaming response)."""
        return self._request("GET", f"/2/drive/{drive_id}/files/{file_id}/download", stream=True)

    def search(self, drive_id: int, query: str) -> Iterator[File]:
        """Search for files by name."""
        body = self._request(
            "GET",
            f"/3/drive/{drive_id}/files/search",
            params={"query": query},
        )
        for f in body.get("data", []):
            yield File.from_api(f)

    def trash_file(self, drive_id: int, file_id: int) -> None:
        """Move a file to trash."""
        self._request("DELETE", f"/2/drive/{drive_id}/files/{file_id}")

    def move_file(
        self,
        drive_id: int,
        file_id: int,
        destination_directory_id: int,
        name: str | None = None,
        conflict: str = "error",
    ) -> MoveOperation:
        """Move a file or directory to another directory.

        kDrive move is async — the API returns a CancelResource with a
        cancel_id that can be polled or canceled. Returns the operation
        handle; does not block on completion.
        """
        json_body: dict[str, Any] = {"conflict": conflict}
        if name is not None:
            json_body["name"] = name
        body = self._request(
            "POST",
            f"/3/drive/{drive_id}/files/{file_id}/move/{destination_directory_id}",
            json_body=json_body,
        )
        return MoveOperation.from_api(body.get("data", {}))

    def copy_file(
        self,
        drive_id: int,
        file_id: int,
        destination_directory_id: int,
        name: str | None = None,
        conflict: str = "rename",
    ) -> File:
        """Copy a file or directory to another directory.

        kDrive copy is synchronous — the response contains the full
        metadata of the newly-created file or directory.
        """
        json_body: dict[str, Any] = {"conflict": conflict}
        if name is not None:
            json_body["name"] = name
        body = self._request(
            "POST",
            f"/3/drive/{drive_id}/files/{file_id}/copy/{destination_directory_id}",
            json_body=json_body,
        )
        return File.from_api(body.get("data", {}))

    def resolve_path(self, drive_id: int, path: str) -> int:
        """Walk a path like 'Documents/Photos' and return the final file_id."""
        parts = [p for p in path.strip("/").split("/") if p]
        current_id = 1
        for part in parts:
            file_list = list(self.list_files(drive_id, current_id))
            match = next((f for f in file_list if f.name == part), None)
            if not match:
                raise KDriveError(f"'{part}' not found in directory {current_id}")
            current_id = match.id
        return current_id


class KDriveError(Exception):
    """Error raised by kDrive API operations."""

    pass
