"""HTTP(S) XMLTV 수집 및 원자적 파일 저장."""
from __future__ import annotations
import gzip
import io
import json
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

MAX_DOWNLOAD = 64 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024


def decode_xmltv_content(
    content: bytes, *, compressed: bool = False,
    max_unpacked: int = MAX_UNPACKED,
) -> bytes:
    """XMLTV gzip 스트림을 안전한 용량까지만 푼다.

    .xml.gz 확장자, gzip magic, HTTP Content-Encoding 중 어느 형태도 지원한다.
    압축 폭탄은 최대 해제 크기 초과 시 중단하고 최종 XMLTV 파일을 건드리지 않는다.
    """
    if not 0 < max_unpacked <= MAX_UNPACKED:
        raise ValueError("압축 해제 제한이 잘못됐습니다.")
    if compressed or content.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
                unpacked = stream.read(max_unpacked + 1)
        except (OSError, EOFError, ValueError) as exc:
            raise ValueError("손상된 gzip XMLTV입니다.") from exc
        if len(unpacked) > max_unpacked:
            raise ValueError("XMLTV 압축 해제 용량이 제한을 초과했습니다.")
        return unpacked
    if len(content) > max_unpacked:
        raise ValueError("XMLTV 크기가 제한을 초과했습니다.")
    return content


def fetch_xml(url: str, max_bytes: int = MAX_DOWNLOAD) -> bytes:
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("HTTP(S) 주소가 필요하며 URL에 사용자명·암호를 넣을 수 없습니다.")
    if max_bytes <= 0 or max_bytes > MAX_DOWNLOAD:
        raise ValueError("다운로드 제한이 잘못됐습니다.")
    request = urllib.request.Request(url, headers={"User-Agent": "EPGCustom/0.3"})
    with urllib.request.urlopen(request, timeout=35) as response:
        content = response.read(max_bytes + 1)
        encoding = (response.headers.get("Content-Encoding") or "").lower()
    if len(content) > max_bytes:
        raise ValueError("다운로드 용량이 제한을 초과했습니다.")
    return decode_xmltv_content(
        content, compressed=parts.path.lower().endswith(".gz") or "gzip" in encoding
    )


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
