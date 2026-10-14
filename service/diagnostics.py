"""EPGCustom 채널별 진단 집계.

정확히 같은 공급원의 같은 XMLTV 원본 채널 ID를 여러 Shyni 채널이
재사용하는 경우만 별도의 '검토 대상'으로 보고한다. 서로 다른 방송이라는
증거가 없으므로 중복 참조를 오류로 단정하지 않는다.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path

MAX_REPORT_BYTES = 8 * 1024 * 1024


def summarize_diagnostics(report: dict) -> dict:
    """신규 진단 필드만 추가하며 기존 0.3.x JSON 구조를 그대로 보존한다."""
    entries = report.get("채널별상태") or []
    groups = defaultdict(list)
    causes = Counter()

    for row in entries:
        row["매핑공유"] = False
        if row.get("연결"):
            provider = row.get("공급원")
            source_id = row.get("원본채널ID")
            if provider and source_id:
                groups[(provider, source_id)].append(row)
        else:
            cause = row.get("미연결사유") or "미확인"
            causes[cause] += 1
            row.setdefault("미연결사유", cause)

    shared = []
    for (provider, source_id), rows in sorted(groups.items(), key=lambda item: item[0]):
        if len(rows) < 2:
            continue
        for row in rows:
            row["매핑공유"] = True
        shared.append({
            "공급원": provider,
            "원본채널ID": source_id,
            "대상채널ID": [row["ID"] for row in rows],
            "대상채널명": [row.get("이름", row["ID"]) for row in rows],
            "대상채널수": len(rows),
            "판정": "검토",
            "설명": "여러 대상 채널이 같은 원본 EPG를 참조합니다. 정상적인 동시송출일 수 있습니다.",
        })

    report["중복매핑"] = shared
    report["진단요약"] = {
        "연결": sum(bool(row.get("연결")) for row in entries),
        "미연결": sum(not row.get("연결") for row in entries),
        "미연결사유별": dict(sorted(causes.items())),
        "원본공유그룹": len(shared),
        "원본공유대상채널": sum(len(group["대상채널ID"]) for group in shared),
    }
    return report


def load_report(path: str | Path) -> tuple[dict | None, str]:
    """큰 보고서·손상된 JSON에서도 FF 화면이 오류 없이 열리게 한다."""
    target = Path(path)
    try:
        with target.open("rb") as reader:
            raw = reader.read(MAX_REPORT_BYTES + 1)
    except FileNotFoundError:
        return None, "아직 EPG 생성 보고서가 없습니다."
    except OSError:
        return None, "보고서 파일을 읽을 수 없습니다."
    if len(raw) > MAX_REPORT_BYTES:
        return None, "보고서가 크기 제한을 초과했습니다."
    try:
        data = json.loads(raw)
    except (UnicodeError, ValueError):
        return None, "생성 보고서의 JSON 형식이 잘못됐습니다."
    if not isinstance(data, dict):
        return None, "생성 보고서가 JSON 객체 형식이 아닙니다."
    return data, ""


def prepare_diagnostics_view(report: dict | None) -> dict:
    """구버전(v0.3.x) JSON도 깨지지 않게 표시할 안전한 화면 입력값."""
    report = report if isinstance(report, dict) else {}
    raw_rows = report.get("채널별상태")
    raw_rows = raw_rows if isinstance(raw_rows, list) else []
    has_details = isinstance(report.get("진단요약"), dict)

    rows, providers, reasons = [], set(), set()
    for raw in raw_rows[:5000]:
        if not isinstance(raw, dict):
            continue
        connected = bool(raw.get("연결"))
        reason = ""
        if not connected:
            reason = str(raw.get("미연결사유") or (
                "이전 보고서: 재생성 필요" if not has_details else "미확인"))
            reasons.add(reason)
        provider = str(raw.get("공급원") or "")
        if provider:
            providers.add(provider)
        row = {
            "ID": str(raw.get("ID") or ""),
            "이름": str(raw.get("이름") or ""),
            "그룹": str(raw.get("그룹") or ""),
            "연결": connected,
            "공급원": provider,
            "편성항목": raw.get("편성항목") if isinstance(raw.get("편성항목"), int) else 0,
            "원본채널ID": str(raw.get("원본채널ID") or ""),
            "원본채널명": str(raw.get("원본채널명") or ""),
            "매칭방식": str(raw.get("매칭방식") or ""),
            "미연결사유": reason,
            "매핑공유": bool(raw.get("매핑공유", False)),
        }
        rows.append(row)

    groups = report.get("중복매핑", [])
    groups = groups if isinstance(groups, list) else []
    summary = report.get("진단요약") if has_details else {}
    if not isinstance(summary, dict):
        summary = {}
    return {
        "rows": rows,
        "limited": len(raw_rows) > len(rows),
        "providers": sorted(providers),
        "reasons": sorted(reasons),
        "shared": groups,
        "summary": summary,
        "detailed": has_details,
        "total": report.get("전체채널", len(rows)),
        "connected": report.get("편성표연결", sum(r["연결"] for r in rows)),
        "unconnected": report.get("편성표미연결", sum(not r["연결"] for r in rows)),
        "generated": str(report.get("생성시각") or ""),
    }
