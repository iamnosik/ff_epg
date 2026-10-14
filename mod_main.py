"""FlaskFarm 메뉴·설정·수동 실행·스케줄러·XMLTV API 제공."""
from __future__ import annotations
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import abort, jsonify, render_template, send_file
from plugin import F, PluginModuleBase, ToolUtil
from .service.core import build_epg
from .service.io import atomic_json, atomic_write, fetch_xml
from .setup import P

_LOCK = threading.Lock()
_KST = timezone(timedelta(hours=9))


def _output_directory() -> Path:
    """Git 저장소가 아니라 FF의 영속적 데이터 디렉터리를 쓴다."""
    return Path(F.config["path_data"]) / "epgcustom"


def _generate() -> dict:
    setting = P.ModelSetting
    m3u_url = (setting.get("main_m3u_url") or "").strip()
    epg_urls = [
        line.strip() for line in (setting.get("main_epg_urls") or "").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not m3u_url or not epg_urls:
        raise ValueError("M3U 주소와 XMLTV 주소를 설정해야 합니다.")
    try:
        aliases = json.loads(setting.get("main_aliases_json") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("채널별 별칭 JSON에 오류가 있습니다.") from exc
    if not isinstance(aliases, dict):
        raise ValueError("채널별 별칭은 JSON 객체여야 합니다.")

    m3u = fetch_xml(m3u_url)
    feeds, failures = [], []
    for number, url in enumerate(epg_urls, 1):
        label = f"공급원{number}"  # API 키가 포함될 수 있는 URL은 절대로 로그에 기록하지 않는다.
        try:
            feeds.append((label, fetch_xml(url)))
        except Exception as exc:
            failures.append({"공급원": label, "오류유형": type(exc).__name__})
            P.logger.warning("%s 다운로드 실패: %s", label, type(exc).__name__)
    if not feeds:
        raise RuntimeError("모든 XMLTV 공급원 다운로드에 실패했습니다.")

    xml, report = build_epg(m3u, feeds, aliases=aliases)
    if not report["편성항목"]:
        raise RuntimeError("현재 유효한 편성표가 없어 직전 결과를 보존합니다.")
    report["수집실패"] = failures
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
        P.logger.info("EPGCustom 생성 완료: 연결=%s, 편성항목=%s",
                      report["편성표연결"], report["편성항목"])
    except Exception as exc:
        P.ModelSetting.set("main_status", "실패")
        P.logger.error("EPGCustom 생성 실패: %s", type(exc).__name__)
    finally:
        _LOCK.release()


class ModuleMain(PluginModuleBase):
    def __init__(self, plugin):
        super().__init__(plugin, name="main", first_menu="setting", scheduler_desc="통합 EPG 자동 생성")
        self.db_default = {
            "main_db_version": "1",
            "main_m3u_url": "",
            "main_epg_urls": "",
            "main_aliases_json": '{"EBS 1": ["EBS1"]}',
            "main_auto_start": "False",
            "main_interval": "0 */6 * * *",
            "main_last_run": "",
            "main_last_summary": "",
            "main_status": "미실행",
        }

    def process_menu(self, sub, req):
        if sub != "setting":
            abort(404)
        arg = P.ModelSetting.to_dict()
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
            if not target.is_file():
                return jsonify({"상태": P.ModelSetting.get("main_status"), "생성보고서": None})
            return send_file(str(target), mimetype="application/json")
        abort(404)

    def scheduler_function(self):
        _run_safe()
