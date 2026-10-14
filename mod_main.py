"""FlaskFarm 메뉴·설정·수동 실행·스케줄러·XMLTV API 제공."""
from __future__ import annotations
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import abort, jsonify, render_template, send_file
from plugin import F, PluginModuleBase, ToolUtil
from .service.core import build_epg, parse_m3u, parse_xmltv, parse_aliases
from .service.diagnostics import load_report, prepare_diagnostics_view
from .service.hybrid import merge_shyni_hybrid
from .service.io import atomic_json, atomic_write, fetch_xml
from .service.sources import (
    DEFAULT_M3U, DEFAULT_EPGS, IPROXY_M3U, KR1_EPG_URL, m3u_setting,
    epg_setting_display, effective_epg_settings, source_url,
)
from .setup import P

_LOCK = threading.Lock()
_KST = timezone(timedelta(hours=9))
_VERIFIED_ALIASES = {
    "EBS 1": ["EBS1"],
    "TV CHOSUN": ["TV조선"],
    "ANIMAX": ["애니맥스"],
    # v0.5.0: 실제 KR1 XMLTV에서 독립적으로 유효 방송 일정을 확인한
    # 동일 채널/브랜드의 한영·띄어쓰기 표기 차이만 추가한다.
    "SK스토아": ["SK stoa"],
    "공영홈쇼핑": ["공영쇼핑"],
    "CJ ONSTYLE": ["CJ 온스타일"],
    "현대홈쇼핑+샵": ["현대홈쇼핑+Shop"],
    # EBS2와 EBS플러스2, CJ ONSTYLE과 CJ ONSTYLE PLUS는 서로 다른 채널이다.
}


def _is_enabled(value, default=True) -> bool:
    if value is None or value == "":
        return default
    return str(value).lower() in ("true", "1", "on", "yes")



def _output_directory() -> Path:
    """Git 저장소가 아니라 FF의 영속적 데이터 디렉터리를 쓴다."""
    return Path(F.config["path_data"]) / "epgcustom"


def _generate() -> dict:
    setting = P.ModelSetting
    # 비어 있는 기존 설정은 안전한 FF 내부 별칭으로 보완하되 DB 값은 덮어쓰지 않는다.
    # API 키와 서버 주소는 FF 실행 시점에만 해석하고 저장하지 않는다.
    m3u_choice = m3u_setting(setting.get("main_m3u_url"))
    m3u_url = source_url(m3u_choice, ToolUtil.make_apikey_url)
    kr1_enabled = _is_enabled(setting.get("main_kr1_enabled"))
    configured_sources = effective_epg_settings(
        setting.get("main_epg_urls"), kr1_enabled=kr1_enabled)
    epg_urls = [source_url(item, ToolUtil.make_apikey_url)
                for item in configured_sources]
    try:
        aliases = json.loads(setting.get("main_aliases_json") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("채널별 별칭 JSON에 오류가 있습니다.") from exc
    if not isinstance(aliases, dict):
        raise ValueError("채널별 별칭은 JSON 객체여야 합니다.")
    # 이전 DB의 채널 별칭을 보존하면서 검증된 기본 별칭을 실행 시점에 사용한다.
    # 사용자가 해당 채널을 설정한 경우 그 값이 우선한다 (빈 배열은 자동 별칭 해제).
    aliases = {**_VERIFIED_ALIASES, **parse_aliases(aliases)}
    prefer_primary = _is_enabled(setting.get("main_prefer_primary"))

    m3u = fetch_xml(m3u_url)
    include_native = str(setting.get("main_hybrid_compatible") or "True").lower() in ("true", "1", "on", "yes")
    channel_diag = {"모드": "지정 M3U", "IProxy추가채널": 0}
    if m3u_choice == DEFAULT_M3U and include_native:
        try:
            native_url = source_url(IPROXY_M3U, ToolUtil.make_apikey_url)
            native_data = fetch_xml(native_url)
            m3u, channel_diag = merge_shyni_hybrid(m3u, native_data)
        except Exception as exc:
            # ff_iproxy2가 없어도 기존 ALive 목록으로 생성할 수 있게 유지한다.
            channel_diag = {"모드": "ALive 폴백", "IProxy추가채널": 0,
                            "IProxy실패유형": type(exc).__name__}
            P.logger.warning("EPGCustom ff_iproxy2 채널 목록 조회 실패: %s", type(exc).__name__)
    channel_count = len(parse_m3u(m3u))
    if channel_count < 1:
        raise ValueError("M3U 응답에 채널이 없습니다. 채널 목록 주소를 확인하세요.")
    P.logger.info("EPGCustom M3U 채널 목록 확인: %s개", channel_count)
    feeds, failures, feed_checks, parsed_feeds = [], [], [], []
    for number, (setting_url, url) in enumerate(zip(configured_sources, epg_urls), 1):
        # 원본 URL/API 키는 로그·진단 파일에 절대 포함하지 않는다.
        label = ("MyEPG" if setting_url == DEFAULT_EPGS[0]
                 else "KR1" if setting_url == KR1_EPG_URL
                 else f"공급원{number}")
        try:
            xml = fetch_xml(url)
            names, programmes = parse_xmltv(xml)
            programme_count = sum(map(len, programmes.values()))
            if not names or not programme_count:
                raise ValueError("XMLTV 응답에 채널 또는 편성 항목이 없습니다.")
            feeds.append((label, xml))
            parsed_feeds.append((label, names, programmes))
            feed_checks.append({"공급원": label, "채널수": len(names), "편성항목": programme_count})
            P.logger.info("EPGCustom %s 연결 확인: 채널=%s, 편성항목=%s",
                          label, len(names), programme_count)
        except Exception as exc:
            failures.append({"공급원": label, "오류유형": type(exc).__name__})
            P.logger.warning("%s 다운로드 실패: %s", label, type(exc).__name__)
    if not feeds:
        raise RuntimeError("모든 XMLTV 공급원 다운로드에 실패했습니다.")

    output = _output_directory()
    # 부분 장애 상태에서 101채널짜리 기존 EPG를 49채널짜리로 덮어쓰지 않는다.
    # 처음 생성하는 경우에만 정상 확보된 공급원으로 제한된 결과를 허용한다.
    if failures and (output / "epgall.xml").is_file():
        raise RuntimeError("EPG 공급원 일부 오류로 이전 정상 XMLTV를 유지합니다.")

    xml, report = build_epg(
        m3u, feeds, aliases=aliases, prefer_primary=prefer_primary,
        parsed_feeds=parsed_feeds)
    if not report["편성항목"]:
        raise RuntimeError("현재 유효한 편성표가 없어 직전 결과를 보존합니다.")
    report["수집실패"] = failures
    report["연결진단"] = {"M3U채널": channel_count, "XMLTV공급원": feed_checks}
    report["채널목록기준"] = ("FF ALive + ff_iproxy2의 Shyni hybrid 호환 ID"
                         if channel_diag["모드"] == "Shyni hybrid 호환"
                         else "지정한 M3U의 채널 ID" if channel_diag["모드"] == "지정 M3U"
                         else "FF ALive 단독 ID (ff_iproxy2 조회 실패)")
    report["채널목록진단"] = channel_diag
    report["생성시각"] = datetime.now(_KST).isoformat(timespec="seconds")
    report["공급원정책"] = {
        "MyEPG우선": prefer_primary,
        "KR1연동": kr1_enabled and KR1_EPG_URL in configured_sources,
        "부분장애시파일보존": True,
    }
    atomic_write(output / "epgall.xml", xml)
    atomic_json(output / "report.json", report)
    setting.set("main_last_run", report["생성시각"])
    mode = report["채널목록진단"]["모드"]
    if mode == "Shyni hybrid 호환":
        mode_note = f" / hybrid 추가 {report['채널목록진단']['IProxy추가채널']}개"
    elif mode == "ALive 폴백":
        mode_note = " / 주의: ff_iproxy2 조회 실패, ALive 기준만 사용"
    else:
        mode_note = " / 사용자 지정 M3U"
    setting.set("main_last_summary",
        f"전체 {report['전체채널']} / 연결 {report['편성표연결']} / "
        f"미연결 {report['편성표미연결']} / 항목 {report['편성항목']}{mode_note}")
    return report


def _run_safe() -> None:
    if not _LOCK.acquire(blocking=False):
        P.logger.info("EPGCustom이 이미 실행 중이라 중복 요청을 건너뜁니다.")
        return
    try:
        P.ModelSetting.set("main_status", "실행 중")
        report = _generate()
        P.ModelSetting.set("main_status", "부분 성공" if report["수집실패"] else "정상")
        P.ModelSetting.set("main_last_error", "")
        P.logger.info("EPGCustom 생성 완료: 연결=%s, 편성항목=%s",
                      report["편성표연결"], report["편성항목"])
    except Exception as exc:
        P.ModelSetting.set("main_status", "실패")
        # 전체 인증 URL, 헤더, 네트워크 예외 메시지는 설정 DB와 화면에 노출하지 않는다.
        # 사용자가 직접 고칠 수 있는 값 검증 오류만 안전한 문구로 표시한다.
        visible = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
        if "://" in visible or "apikey" in visible.lower():
            visible = type(exc).__name__
        P.ModelSetting.set("main_last_error", visible[:160])
        P.logger.error("EPGCustom 생성 실패: %s", type(exc).__name__)
    finally:
        _LOCK.release()


class ModuleMain(PluginModuleBase):
    def __init__(self, plugin):
        super().__init__(plugin, name="main", first_menu="setting", scheduler_desc="통합 EPG 자동 생성")
        self.db_default = {
            "main_db_version": "1",
            "main_m3u_url": DEFAULT_M3U,
            "main_epg_urls": "\n".join(DEFAULT_EPGS),
            "main_hybrid_compatible": "True",
            "main_kr1_enabled": "True",
            "main_prefer_primary": "True",
            "main_aliases_json": '{"EBS 1": ["EBS1"]}',
            "main_auto_start": "False",
            "main_interval": "0 */6 * * *",
            "main_last_run": "",
            "main_last_summary": "",
            "main_status": "미실행",
            "main_last_error": "",
        }

    def process_menu(self, sub, req):
        if sub == "diagnostics":
            report, error = load_report(_output_directory() / "report.json")
            arg = prepare_diagnostics_view(report)
            arg["report_error"] = error
            arg["current_status"] = P.ModelSetting.get("main_status") or "미실행"
            arg["current_error"] = P.ModelSetting.get("main_last_error") or ""
            return render_template("epgcustom_main_diagnostics.html", arg=arg)
        if sub != "setting":
            abort(404)
        arg = P.ModelSetting.to_dict() or {}
        # 기존 DB의 빈 설정에도 기본값을 보여준다. 저장된 사용자 지정 URL은 보존한다.
        arg["main_m3u_url"] = m3u_setting(arg.get("main_m3u_url"))
        arg["main_epg_urls"] = epg_setting_display(arg.get("main_epg_urls"))
        arg["main_hybrid_compatible"] = arg.get("main_hybrid_compatible") or "True"
        arg["main_kr1_enabled"] = arg.get("main_kr1_enabled") or "True"
        arg["main_prefer_primary"] = arg.get("main_prefer_primary") or "True"
        arg["is_include"] = F.scheduler.is_include(self.get_scheduler_name())
        arg["is_running"] = F.scheduler.is_running(self.get_scheduler_name())
        arg["api_epgall"] = ToolUtil.make_apikey_url("/epgcustom/api/epgall")
        arg["api_status"] = ToolUtil.make_apikey_url("/epgcustom/api/status")
        return render_template("epgcustom_main_setting.html", arg=arg)

    def process_command(self, command, arg1, arg2, arg3, req):
        if command != "make":
            return jsonify({"ret": "warning", "msg": "알 수 없는 명령입니다."})
        if _LOCK.locked():
            return jsonify({"ret": "warning", "msg": "이미 생성 작업을 수행 중입니다."})
        threading.Thread(target=_run_safe, name="EPGCustomGeneration", daemon=True).start()
        return jsonify({"ret": "success", "msg": "EPG 생성 작업을 시작했습니다."})

    def process_api(self, sub, req):
        directory = _output_directory()
        if sub == "epgall":
            target = directory / "epgall.xml"
            if not target.is_file():
                abort(404, "EPG 파일이 없습니다. 먼저 생성하세요.")
            return send_file(str(target), mimetype="application/xml")
        if sub == "status":
            latest, error = load_report(directory / "report.json")
            return jsonify({
                "상태": P.ModelSetting.get("main_status"),
                "마지막오류": P.ModelSetting.get("main_last_error") or "",
                "최근성공시각": P.ModelSetting.get("main_last_run") or "",
                "생성보고서": latest,
                "보고서오류": error,
            })
        abort(404)

    def scheduler_function(self):
        _run_safe()
