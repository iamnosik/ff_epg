"""Shyni hybrid M3U와 같은 채널 ID 목록을 FF ALive와 ff_iproxy2에서 만든다.

방송 재생/프록시는 수행하지 않는다. 채널 메타데이터만 조합해 EPG의
XMLTV channel id가 Shyni에 등록되는 tvg-id와 일치하도록 한다.
"""
from __future__ import annotations

from .core import parse_m3u


def _pairs(data: bytes | str):
    text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data.lstrip("\ufeff")
    pending = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            pending = raw
        elif line and not line.startswith("#") and pending is not None:
            name = pending.rsplit(",", 1)[-1].strip()
            if name:
                yield pending, raw, name
            pending = None


def merge_shyni_hybrid(alive_m3u: bytes | str, iproxy_m3u: bytes | str) -> tuple[bytes, dict]:
    """현행 hybrid proxy의 목록 생성 규칙에 따라 ALive+iproxy M3U를 합친다.

    1) ALive 목록 중 'KBS 1TV'와 'KBS 2TV' 표시명만 제거
    2) iproxy2 채널은 ALive에 없는 *표시명*만 추가
    3) 신규 iproxy 채널 ID는 tvg-name을 사용
    """
    existing = list(_pairs(alive_m3u))
    native = list(_pairs(iproxy_m3u))
    if not existing:
        raise ValueError("ALive M3U에 유효한 채널이 없습니다.")
    if not native:
        raise ValueError("ff_iproxy2 M3U에 유효한 채널이 없습니다.")

    keep = [(meta, stream, name) for meta, stream, name in existing
            if name not in ("KBS 1TV", "KBS 2TV")]
    output = ["#EXTM3U"]
    for meta, stream, _ in keep:
        output.extend((meta, stream))
    found_names = {name for _, _, name in keep}

    # iproxy는 소스 순서를 유지하며 같은 이름은 한 번만 추가한다.
    # 실제 Shyni hybrid에서도 신규 채널에 tvg-name을 설정한다.
    added = 0
    for _meta, stream, name in native:
        if name in found_names:
            continue
        safe_name = name.replace('"', "")
        output.append(f'#EXTINF:-1 tvg-name="{safe_name}",{name}')
        output.append(stream)
        found_names.add(name)
        added += 1

    combined = ("\n".join(output) + "\n").encode("utf-8")
    return combined, {
        "모드": "Shyni hybrid 호환",
        "ALive원본항목": len(existing),
        "IProxy원본항목": len(native),
        "IProxy추가채널": added,
        "중복KBS제외": len(existing) - len(keep),
        "최종채널ID": len(parse_m3u(combined)),
    }
