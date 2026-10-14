"""HTTP(S) XMLTV 수집 및 원자적 파일 저장."""
from __future__ import annotations
import json
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

MAX_DOWNLOAD = 64 * 1024 * 1024


def fetch_xml(url: str, max_bytes: int = MAX_DOWNLOAD) -> bytes:
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("HTTP(S) 주소가 필요하며 URL에 사용자명·암호를 넣을 수 없습니다.")
    if max_bytes <= 0 or max_bytes > MAX_DOWNLOAD:
        raise ValueError("다운로드 제한이 잘못됐습니다.")
    request = urllib.request.Request(url, headers={"User-Agent": "EPGCustom/0.1"})
    with urllib.request.urlopen(request, timeout=35) as response:
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError("다운로드 용량이 제한을 초과했습니다.")
    return content


def atomic_write(path: str | Path, content: bytes) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".epgcustom-", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def atomic_json(path: str | Path, value: dict) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
