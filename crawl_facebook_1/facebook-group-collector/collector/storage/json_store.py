"""
collector/storage/json_store.py — Async JSON file read/write helpers.

All I/O is async (aiofiles). Writes are atomic via temp-file rename.
JSON files are pretty-printed (indent=2) for human readability.

This module is the lowest-level I/O layer.
Higher-level repository classes (GroupRepo, PostRepo, etc.) use this.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import aiofiles

logger = logging.getLogger(__name__)

# Global write lock per file path — prevents concurrent corruption
_file_locks: dict[str, asyncio.Lock] = {}


def _get_lock(path: str) -> asyncio.Lock:
    if path not in _file_locks:
        _file_locks[path] = asyncio.Lock()
    return _file_locks[path]


async def read_json(path: Path) -> dict | list | None:
    """
    Read and parse a JSON file. Returns None if file does not exist.
    Raises JSONDecodeError if file is malformed.
    """
    if not path.exists():
        return None
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        content = await f.read()
    return json.loads(content)


async def write_json(path: Path, data: Any) -> None:
    """
    Write data to a JSON file atomically (write to temp, then rename).
    Creates parent directories if needed.
    Thread-safe via per-file asyncio.Lock.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lock = _get_lock(str(path))
    async with lock:
        # Write to a temp file in the same directory, then rename
        # This ensures the file is never in a half-written state
        tmp_path = path.with_suffix(".tmp")
        try:
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
                await f.flush()
            # Atomic rename
            os.replace(tmp_path, path)
        except Exception:
            # Clean up temp file on error
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise


async def read_index(path: Path) -> dict:
    """
    Read a JSON index file (key->value map). Returns empty dict if not found.
    Index files are always dicts.
    """
    data = await read_json(path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        logger.warning("Index file %s is not a dict — resetting", path)
        return {}
    return data


async def update_index(path: Path, updates: dict) -> None:
    """
    Merge `updates` into the index file at `path`.
    Creates the index if it doesn't exist.
    Thread-safe.
    """
    lock = _get_lock(str(path))
    async with lock:
        # Read current state
        current = {}
        if path.exists():
            try:
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
                current = json.loads(content)
            except (json.JSONDecodeError, IOError):
                current = {}

        current.update(updates)

        # Atomic write
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        try:
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(current, ensure_ascii=False, indent=2))
                await f.flush()
            os.replace(tmp_path, path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise


async def list_json_files(directory: Path) -> list[Path]:
    """List all .json files in a directory (non-recursive)."""
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


async def file_exists(path: Path) -> bool:
    return path.exists()
