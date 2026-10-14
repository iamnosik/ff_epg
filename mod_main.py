"""FlaskFarm 메뉴·설정·수동 실행·스케줄러·XMLTV API 제공."""
from __future__ import annotations
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import abort, jsonify, render_template, send_file
from plugin import F, PluginModuleBase, ToolUtil
from .service.core import build_epg, parse_m3u, parse_xmltv
from .service.io import atomic_json, atomic_write, fetch_xml
from .service.sources import (
    DEFAULT_M3U, DEFAULT_EPGS, m3u_setting, epg_settings,
    epg_setting_display, source_url,
)
from .setup import P

_LOCK = threading.Lock()
_KST = timezone(timedelta(hours=9))


def _output_directory() -> Path:
    """Git 저장소가 아니라 FF의 영속적 데이터 디렉터리를 쓴다."""
    return Path(F.config["path_data"]) / "epgcustom"


def _generate() -> dict:
    setting = P.ModelSetting
    # 비어 있는 기존 설정은 안전한 FF 내부 별칭으로 보완하되 DB 값은 덮어쓰지 않는다.
    # API 키와 서버 주소는 FF 실행 시점에만 해석하고 저장하지 않는다.
    m3u_url = source_url(m3u_setting(setting.get("main_m3u_url")), ToolUtil.make_apikey_url)
    epg_urls = [source_url(item, ToolUtil.make_apikey_url)
                for item in epg_settings(setting.get("main_epg_urls"))]
    try:
        aliases = json.loads(setting.get("main_aliases_json") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("채널별 별칭 JSON에 오류가 있습니다.") from exc
    if not isinstance(aliases, dict):
        raise ValueError("채널별 별칭은 JSON 객체여야 합니다.")

    m3u = fetch_xml(m3u_url)
    channel_count = len(parse_m3u(m3u))
    if channel_count < 1:
        raise ValueError("M3U 응답에 채널이 없습니다. 채널 목록 주소를 확인하세요.")
    P.logger.info("EPGCustom M3U 채널 목록 확인: %s개", channel_count)
    feeds, failures, feed_checks = [], [], []
    for number, url in enumerate(epg_urls, 1):
        label = f"공급원{number}"  # API 키가 포함될 수 있는 URL은 절대로 로그에 기록하지 않는다.
        try:
            xml = fetch_xml(url)
            names, programmes = parse_xmltv(xml)
            programme_count = sum(map(len, programmes.values()))
            if not names or not programme_count:
                raise ValueError("XMLTV 응답에 채널 또는 편성 항목이 없습니다.")
            feeds.append((label, xml))
            feed_checks.append({"공급원": label, "채널수": len(names), "편성항목": programme_count})
            P.logger.info("EPGCustom %s 연결 확인: 채널=%s, 편성항목=%s",
                          label, len(names), programme_count)
        except Exception as exc:
            failures.append({"공급원": label, "오류유형": type(exc).__name__})
            P.logger.warning("%s 다운로드 실패: %s", label, type(exc).__name__)
    if not feeds:
        raise RuntimeError("모든 XMLTV 공급원 다운로드에 실패했습니다.")

    xml, report = build_epg(m3u, feeds, aliases=aliases)
    if not report["편성항목"]:
        raise RuntimeError("현재 유효한 편성표가 없어 직전 결과를 보존합니다.")
    report["수집실패"] = failures
    report["연결진단"] = {"M3U채널": channel_count, "XMLTV공급원": feed_checks}
    report["채널목록기준"] = "설정된 M3U의 tvg-id (기본값은 FF ALive)"
    report["생성시각"] = datetime.now(_KST).isoformat(timespec="seconds")
    output = _output_directory()
    atomic_write(output / "epgall.xml", xml)
    atomic_json(output / "report.json", report)
    setting.set("main_last_run", report["생성시각"])
    setting.set("main_last_summary",
        f"전체 {report['전체채널']} / 연결 {report['편성표연결']} / "
        f"미연결 {report['편성표미연결']} / 항목 {report['편성항목']}")
    return report


def _run_safe() -> None:
    if not _LOCK.acquire(blocking=False):
        P.logger.info("EPGCustom이 이미 실행 중이라 중복 요청을 건너뜁니다.")
        return
    try:
        P.ModelSetting.set("main_status", "실행 중")
        report = _generate()
        P.ModelSetting.set("main_status", "정상")
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
            "main_aliases_json": '{"EBS 1": ["EBS1"]}',
            "main_auto_start": "False",
            "main_interval": "0 */6 * * *",
            "main_last_run": "",
            "main_last_summary": "",
            "main_status": "미실행",
            "main_last_error": "",
        }

    def process_menu(self, sub, req):
        if sub != "setting":
            abort(404)
        arg = P.ModelSetting.to_dict() or {}
        # 기존 DB의 빈 설정에도 기본값을 보여준다. 저장된 사용자 지정 URL은 보존한다.
        arg["main_m3u_url"] = m3u_setting(arg.get("main_m3u_url"))
        arg["main_epg_urls"] = epg_setting_display(arg.get("main_epg_urls"))
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
            target = directory / "report.json"
            latest = None
            if target.is_file():
                try:
                    latest = json.loads(target.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    P.logger.warning("EPGCustom 마지막 진단 보고서 읽기 실패")
            return jsonify({
                "상태": P.ModelSetting.get("main_status"),
                "마지막오류": P.ModelSetting.get("main_last_error") or "",
                "최근성공시각": P.ModelSetting.get("main_last_run") or "",
                "생성보고서": latest,
            })
        abort(404)

    def scheduler_function(self):
        _run_safe()
