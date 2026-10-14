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


def summarize_groups(entries: list[dict]) -> list[dict]:
    """M3U 그룹별 연결 현황. 원본 그룹명은 보존하고 비어 있으면 그룹 없음으로 집계.

    채널 수는 M3U의 고유 채널 ID 기준이며, 같은 원본 EPG 공유도 별도
    채널이므로 각각 계산한다. 미연결 수가 많은 그룹부터 표시한다.
    """
    grouped = {}
    for row in entries:
        if not isinstance(row, dict):
            continue
        group = str(row.get("그룹") or "").strip() or "그룹 없음"
        summary = grouped.setdefault(group, {
            "그룹": group, "전체": 0, "연결": 0, "미연결": 0,
            "연결률": 0.0, "미연결사유별": {},
        })
        summary["전체"] += 1
        if row.get("연결"):
            summary["연결"] += 1
        else:
            summary["미연결"] += 1
            reason = str(row.get("미연결사유") or "미확인")
            summary["미연결사유별"][reason] = summary["미연결사유별"].get(reason, 0) + 1
    for summary in grouped.values():
        if summary["전체"]:
            summary["연결률"] = round(100 * summary["연결"] / summary["전체"], 1)
        summary["미연결사유별"] = dict(sorted(summary["미연결사유별"].items()))
    return sorted(grouped.values(), key=lambda group: (-group["미연결"], -group["전체"], group["그룹"]))


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
    report["그룹별요약"] = summarize_groups(entries)
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
            "그룹표시": str(raw.get("그룹") or "").strip() or "그룹 없음",
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

    # 구버전(v0.4.x) JSON은 그룹별요약이 없으므로 화면에서 즉시 계산한다.
    # 저장된 그룹별요약을 무조건 신뢰하지 않아 오래된/손상된 값을 표시하지 않는다.
    group_summary = summarize_groups(rows)
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
        "groups": sorted((group["그룹"] for group in group_summary)),
        "group_summary": group_summary,
        "top_missing_groups": [group for group in group_summary if group["미연결"]][:5],
        "shared": groups,
        "summary": summary,
        "detailed": has_details,
        "total": report.get("전체채널", len(rows)),
        "connected": report.get("편성표연결", sum(r["연결"] for r in rows)),
        "unconnected": report.get("편성표미연결", sum(not r["연결"] for r in rows)),
        "generated": str(report.get("생성시각") or ""),
    }
