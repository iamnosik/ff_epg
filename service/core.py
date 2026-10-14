"""EPGCustom XMLTV 통합 엔진. FF 프레임워크에 의존하지 않아 독립 테스트할 수 있다."""
from __future__ import annotations
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

_ATTR = re.compile(r'([\w-]+)="([^"]*)"')
_TIME = re.compile(r'^(\d{12}|\d{14})(?:\s*([+-])(\d{2})(\d{2}))?')
_KST = timezone(timedelta(hours=9))


def normalize_name(value: str) -> str:
    """대소문자·공백·구두점만 보정. 다른 채널로 자동 추정하지 않는다."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(ch for ch in value if ch.isalnum())


def parse_m3u(data: bytes | str) -> list[dict[str, str]]:
    """Shyni와 동일하게 tvg-id, tvg-name, 표시명 순서로 채널 ID를 결정."""
    text = data.decode("utf-8-sig") if isinstance(data, bytes) else data.lstrip("\ufeff")
    channels = []
    waiting = None
    seen = set()
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            attrs = dict(_ATTR.findall(line))
            display = line.rsplit(",", 1)[-1].strip() or attrs.get("tvg-name") or "채널"
            waiting = attrs, display
        elif line and not line.startswith("#") and waiting is not None:
            attrs, display = waiting
            cid = (attrs.get("tvg-id") or attrs.get("tvg-name") or display).strip()
            if cid and cid not in seen:
                seen.add(cid)
                channels.append({
                    "id": cid, "name": display,
                    "group": attrs.get("group-title", ""),
                    "logo": attrs.get("tvg-logo", ""),
                })
            waiting = None
    return channels


def parse_xmltv(data: bytes) -> tuple[dict[str, str], dict[str, list[ET.Element]]]:
    """원본 XMLTV 채널·프로그램을 분리해 읽는다."""
    names = {}
    programmes = defaultdict(list)
    for _, elem in ET.iterparse(io.BytesIO(data), events=("end",)):
        if elem.tag == "channel":
            cid = (elem.get("id") or "").strip()
            if cid:
                names[cid] = (elem.findtext("display-name") or cid).strip()
            elem.clear()
        elif elem.tag == "programme":
            cid = (elem.get("channel") or "").strip()
            if cid and elem.get("start") and elem.get("stop"):
                programmes[cid].append(ET.fromstring(ET.tostring(elem, encoding="utf-8")))
            elem.clear()
    return names, programmes


def xmltv_time(raw: str) -> datetime | None:
    match = _TIME.match((raw or "").strip())
    if not match:
        return None
    digits, sign, hour, minute = match.groups()
    if len(digits) == 12:
        digits += "00"
    try:
        dt = datetime.strptime(digits, "%Y%m%d%H%M%S")
        zone = _KST
        if sign:
            offset = timedelta(hours=int(hour), minutes=int(minute))
            zone = timezone(offset if sign == "+" else -offset)
        return dt.replace(tzinfo=zone)
    except (ValueError, OverflowError):
        return None


def parse_aliases(value: dict[str, Any] | None) -> dict[str, list[str]]:
    """사용자가 지정한 별칭만 추가한다."""
    result = {}
    for channel, aliases in (value or {}).items():
        if not isinstance(channel, str) or not isinstance(aliases, list):
            raise ValueError('별칭은 {"채널명": ["다른 이름"]} 형식이어야 합니다.')
        if not all(isinstance(a, str) and a.strip() for a in aliases):
            raise ValueError(f"{channel}: 별칭은 비어 있지 않은 문자열이어야 합니다.")
        result[channel] = aliases
    return result


def _make_index(names, programmes):
    index = defaultdict(set)
    for cid, display in names.items():
        if not programmes.get(cid):
            continue
        for name in (cid, display):
            key = normalize_name(name)
            if key:
                index[key].add(cid)
    return index


def _match_id(channel, names, programmes, index, aliases):
    if programmes.get(channel["id"]):
        return channel["id"]
    options = [channel["name"], channel["id"]]
    options.extend(aliases.get(channel["name"], []))
    options.extend(aliases.get(channel["id"], []))
    for option in options:
        matches = index.get(normalize_name(option), set())
        if len(matches) == 1:
            return next(iter(matches))
    return None


def build_epg(
    m3u: bytes | str, feeds: list[tuple[str, bytes]],
    aliases: dict[str, list[str]] | None = None,
    now: datetime | None = None, forward_days: int = 8,
) -> tuple[bytes, dict[str, Any]]:
    """상위 공급원에 유효한 편성표가 없으면 다음 공급원으로 대체한다."""
    channels = parse_m3u(m3u)
    if not channels:
        raise ValueError("유효한 M3U 채널이 없습니다.")
    if not feeds:
        raise ValueError("EPG 공급원이 설정되지 않았습니다.")
    aliases = parse_aliases(aliases)
    now = now or datetime.now(_KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_KST)
    oldest = now - timedelta(hours=2)
    newest = now + timedelta(days=forward_days)
    prepared = []
    for label, xml in feeds:
        names, programmes = parse_xmltv(xml)
        prepared.append((label, names, programmes, _make_index(names, programmes)))
    tv = ET.Element("tv", {"generator-info-name": "EPGCustom v0.1.3"})
    report = {
        "전체채널": len(channels), "편성표연결": 0, "편성표미연결": 0,
        "편성항목": 0, "공급원별연결": {name: 0 for name, _ in feeds},
        "미연결채널": [],
    }
    for channel in channels:
        node = ET.SubElement(tv, "channel", {"id": channel["id"]})
        ET.SubElement(node, "display-name").text = channel["name"]
        if channel["logo"]:
            ET.SubElement(node, "icon", {"src": channel["logo"]})
    for channel in channels:
        selected, provider = [], None
        for label, names, programmes, index in prepared:
            cid = _match_id(channel, names, programmes, index, aliases)
            if cid is None:
                continue
            current, seen = [], set()
            for item in programmes.get(cid, []):
                start = xmltv_time(item.get("start", ""))
                stop = xmltv_time(item.get("stop", ""))
                if start is None or stop is None or stop <= start:
                    continue
                if stop < oldest or start > newest:
                    continue
                title = (item.findtext("title") or "").strip()
                key = (item.get("start", ""), item.get("stop", ""), title)
                if key in seen:
                    continue
                seen.add(key)
                current.append(item)
            if current:
                provider, selected = label, current
                break
        if not selected:
            report["편성표미연결"] += 1
            report["미연결채널"].append({"이름": channel["name"], "ID": channel["id"]})
            continue
        report["편성표연결"] += 1
        report["공급원별연결"][provider] += 1
        for item in sorted(selected, key=lambda e: e.get("start", "")):
            item.set("channel", channel["id"])
            tv.append(item)
        report["편성항목"] += len(selected)
    return ET.tostring(tv, encoding="utf-8", xml_declaration=True), report
