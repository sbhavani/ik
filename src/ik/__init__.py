"""Infomaniak kDrive API client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "used_size": self.used_size,
            "is_locked": self.is_locked,
            "has_operation_in_progress": self.has_operation_in_progress,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "is_directory": self.is_directory,
            "parent_id": self.parent_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "mime_type": self.mime_type,
        }


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "cancel_id": self.cancel_id,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
        }


@dataclass
class ShareLink:
    """Public share link for a kDrive file.

    Returned by the get/create/update endpoints. Unix timestamps from the
    API (`created_at`, `updated_at`, `valid_until`) are converted to
    `datetime` for ergonomic use; pass `None` to `update_share_link` to
    clear `valid_until`.
    """

    url: str
    file_id: int
    right: str
    valid_until: datetime | None
    can_download: bool
    can_edit: bool
    can_see_info: bool
    can_comment: bool
    can_request_access: bool
    can_see_stats: bool
    access_blocked: bool
    created_at: datetime | None
    updated_at: datetime | None
    created_by: int | None
    views: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ShareLink:
        def ts(key: str) -> datetime | None:
            v = data.get(key)
            return datetime.fromtimestamp(v) if v else None

        return cls(
            url=data.get("url", ""),
            file_id=data.get("file_id", 0),
            right=data.get("right", "public"),
            valid_until=ts("valid_until"),
            can_download=bool(data.get("capabilities", {}).get("can_download", False)),
            can_edit=bool(data.get("capabilities", {}).get("can_edit", False)),
            can_see_info=bool(data.get("capabilities", {}).get("can_see_info", False)),
            can_comment=bool(data.get("capabilities", {}).get("can_comment", False)),
            can_request_access=bool(data.get("capabilities", {}).get("can_request_access", False)),
            can_see_stats=bool(data.get("capabilities", {}).get("can_see_stats", False)),
            access_blocked=bool(data.get("access_blocked", False)),
            created_at=ts("created_at"),
            updated_at=ts("updated_at"),
            created_by=data.get("created_by"),
            views=data.get("views", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "file_id": self.file_id,
            "right": self.right,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "capabilities": {
                "can_download": self.can_download,
                "can_edit": self.can_edit,
                "can_see_info": self.can_see_info,
                "can_comment": self.can_comment,
                "can_request_access": self.can_request_access,
                "can_see_stats": self.can_see_stats,
            },
            "access_blocked": self.access_blocked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "views": self.views,
        }


@dataclass
class SharedFile:
    """A file that has a share link, from the list endpoint.

    Different shape from `File` — fewer fields, no mime_type or paths.
    """

    id: int
    name: str
    update_at: datetime | None
    users: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> SharedFile:
        ts = data.get("update_at")
        return cls(
            id=data.get("id", 0),
            name=data.get("name", "?"),
            update_at=datetime.fromtimestamp(ts) if ts else None,
            users=data.get("users", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "update_at": self.update_at.isoformat() if self.update_at else None,
            "users": self.users,
        }


_UNSET: Any = object()
"""Sentinel for distinguishing 'argument not passed' from 'argument is None'.

Used by `update_share_link` so callers can clear nullable fields (e.g.
`valid_until=None` to remove an expiry) without also clearing fields they
simply didn't pass.
"""


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

    def upload_file_streaming(
        self,
        drive_id: int,
        directory_id: int,
        file_name: str,
        file_path: Path,
        chunk_size: int = 8 * 1024 * 1024,
        conflict: str = "error",
        on_progress: Callable[[int, int], None] | None = None,
    ) -> File:
        """Upload a file via the chunked session flow, streaming from disk.

        Three calls: start → (chunk × ceil(total/chunk_size)) → finish.
        The file is read in fixed-size chunks; the whole file is never
        held in memory. The on_progress callback is invoked after each
        chunk with (bytes_sent, total_size); pass None to skip.
        """
        total_size = file_path.stat().st_size
        if total_size == 0:
            total_chunks = 0
        else:
            total_chunks = (total_size + chunk_size - 1) // chunk_size

        start = self._request(
            "POST",
            f"/3/drive/{drive_id}/upload/session/start",
            json_body={
                "directory_id": directory_id,
                "file_name": file_name,
                "total_size": total_size,
                "total_chunks": total_chunks,
                "conflict": conflict,
            },
        )
        session_token = start["data"]["session_token"]

        sent = 0
        with open(file_path, "rb") as f:
            for chunk_number in range(1, total_chunks + 1):
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                self._request(
                    "POST",
                    f"/3/drive/{drive_id}/upload/session/{session_token}/chunk",
                    params={"chunk_number": chunk_number, "chunk_size": len(chunk)},
                    data=chunk,
                )
                sent += len(chunk)
                if on_progress is not None:
                    on_progress(sent, total_size)

        finish = self._request(
            "POST",
            f"/3/drive/{drive_id}/upload/session/{session_token}/finish",
            json_body={},
        )
        return File.from_api(finish.get("data", {}))

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

    # ── Share Link Operations ──────────────────────────────────────────

    def get_share_link(self, drive_id: int, file_id: int) -> ShareLink:
        """Get the share link for a file (404 if no link exists)."""
        body = self._request("GET", f"/2/drive/{drive_id}/files/{file_id}/link")
        return ShareLink.from_api(body.get("data", {}))

    def create_share_link(
        self,
        drive_id: int,
        file_id: int,
        *,
        right: str = "public",
        password: str | None = None,
        valid_until: int | None = None,
        can_download: bool = True,
        can_edit: bool = False,
        can_see_info: bool = False,
        can_comment: bool = False,
        can_request_access: bool = False,
        can_see_stats: bool = False,
    ) -> ShareLink:
        """Create a public share link for a file.

        `right` is one of `public`, `password`, `inherit`. When `password`,
        the `password` arg is required. `valid_until` is a Unix timestamp
        (or None for no expiry).
        """
        body: dict[str, Any] = {
            "right": right,
            "password": password,
            "valid_until": valid_until,
            "can_download": can_download,
            "can_edit": can_edit,
            "can_see_info": can_see_info,
            "can_comment": can_comment,
            "can_request_access": can_request_access,
            "can_see_stats": can_see_stats,
        }
        resp = self._request("POST", f"/2/drive/{drive_id}/files/{file_id}/link", json_body=body)
        return ShareLink.from_api(resp.get("data", {}))

    def update_share_link(
        self,
        drive_id: int,
        file_id: int,
        *,
        right: str | None = None,
        password: str | None = None,
        valid_until: Any = _UNSET,
        can_download: bool | None = None,
        can_edit: bool | None = None,
        can_see_info: bool | None = None,
        can_comment: bool | None = None,
        can_request_access: bool | None = None,
        can_see_stats: bool | None = None,
    ) -> ShareLink:
        """Partially update a share link. Only fields that are not `_UNSET`
        are sent; pass `valid_until=None` to clear an existing expiry.
        """
        body: dict[str, Any] = {}
        if right is not None:
            body["right"] = right
        if password is not None:
            body["password"] = password
        if valid_until is not _UNSET:
            body["valid_until"] = valid_until
        if can_download is not None:
            body["can_download"] = can_download
        if can_edit is not None:
            body["can_edit"] = can_edit
        if can_see_info is not None:
            body["can_see_info"] = can_see_info
        if can_comment is not None:
            body["can_comment"] = can_comment
        if can_request_access is not None:
            body["can_request_access"] = can_request_access
        if can_see_stats is not None:
            body["can_see_stats"] = can_see_stats

        resp = self._request("PUT", f"/2/drive/{drive_id}/files/{file_id}/link", json_body=body)
        return ShareLink.from_api(resp.get("data", {}))

    def delete_share_link(self, drive_id: int, file_id: int) -> None:
        """Remove the share link for a file."""
        self._request("DELETE", f"/2/drive/{drive_id}/files/{file_id}/link")

    def list_shared_files(self, drive_id: int) -> Iterator[SharedFile]:
        """List files in the drive that have a share link, paginated."""
        cursor = None
        while True:
            params: dict[str, Any] = {}
            if cursor:
                params["cursor"] = cursor
            body = self._request("GET", f"/3/drive/{drive_id}/files/links", params=params)
            for f in body.get("data", []):
                yield SharedFile.from_api(f)
            if not body.get("has_more", False):
                break
            cursor = body.get("cursor")

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
