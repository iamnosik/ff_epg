"""FlaskFarm 설치 없이 FF 설정 화면과 편성표 생성 흐름을 검증한다."""
from __future__ import annotations

import importlib.util
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
M3U = """#EXTM3U
#EXTINF:-1 tvg-id="EBS 1" tvg-name="EBS 1" group-title="지상파",EBS 1
https://example.invalid/stream
"""
XMLTV = b"""<?xml version="1.0" encoding="utf-8"?>
<tv>
  <channel id="EBS1"><display-name>EBS1</display-name></channel>
  <programme channel="EBS1" start="20261014090000 +0900" stop="20261014110000 +0900">
    <title>EBS test</title>
  </programme>
</tv>
"""


class DummySetting:
    values = {}

    @classmethod
    def get(cls, name):
        return cls.values.get(name)

    @classmethod
    def set(cls, name, value):
        cls.values[name] = value

    @classmethod
    def to_dict(cls):
        return dict(cls.values)


class DummyScheduler:
    def is_include(self, name):
        return False

    def is_running(self, name):
        return False


class DummyBase:
    def __init__(self, plugin, name, first_menu=None, scheduler_desc=None):
        self.P = plugin
        self.name = name

    def get_scheduler_name(self):
        return "epgcustom_main"


class RuntimeFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        DummySetting.values = {"main_m3u_url": "", "main_epg_urls": "", "main_aliases_json": "{}", "main_kr1_enabled": "False"}
        self.url_reads = []
        self.fake_f = types.SimpleNamespace(
            config={"path_data": self.tmp.name},
            scheduler=DummyScheduler(),
        )
        self.fake_p = types.SimpleNamespace(
            ModelSetting=DummySetting,
            logger=logging.getLogger("epgcustom-tests"),
        )

        package = types.ModuleType("epgcustom_runtime_test")
        package.__path__ = [str(ROOT)]
        setup = types.ModuleType("epgcustom_runtime_test.setup")
        setup.P = self.fake_p
        plugin = types.ModuleType("plugin")
        plugin.F = self.fake_f
        plugin.PluginModuleBase = DummyBase
        plugin.ToolUtil = types.SimpleNamespace(
            make_apikey_url=lambda path: "https://ff.example.test" + path + ("&" if "?" in path else "?") + "apikey=RUNTIME_TEST"
        )
        flask = types.ModuleType("flask")
        flask.abort = lambda code, msg=None: None
        flask.jsonify = lambda data: data
        flask.render_template = lambda template, arg: {"template": template, "arg": arg}
        flask.send_file = lambda *args, **kwargs: None
        overrides = {
            "epgcustom_runtime_test": package,
            "epgcustom_runtime_test.setup": setup,
            "plugin": plugin,
            "flask": flask,
        }
        with patch.dict(sys.modules, overrides):
            spec = importlib.util.spec_from_file_location(
                "epgcustom_runtime_test.mod_main", ROOT / "mod_main.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        # 실제 시스템 시각과 무관하도록 고정된 EPG 시험 시각을 사용한다.
        from datetime import datetime, timedelta, timezone
        builder = module.build_epg
        fixed_now = datetime(2026, 10, 14, 10, 0, tzinfo=timezone(timedelta(hours=9)))
        module.build_epg = lambda *args, **kwargs: builder(*args, now=fixed_now, **kwargs)
        self.module = module

    def _fetch(self, url):
        self.url_reads.append(url)
        if url.endswith("/alive/api/m3u?apikey=RUNTIME_TEST"):
            return M3U.encode()
        if url.endswith("/myepg/api/epgall?apikey=RUNTIME_TEST"):
            return XMLTV
        if url.endswith("/epg/api/xml/alive?apikey=RUNTIME_TEST"):
            return b"<broken"
        raise ValueError("예상하지 못한 시험 URL")

    def test_empty_configuration_shows_readable_defaults(self):
        response = self.module.ModuleMain(self.fake_p).process_menu("setting", None)
        arg = response["arg"]
        self.assertEqual(arg["main_m3u_url"], "ff://alive/api/m3u")
        self.assertIn("ff://myepg/api/epgall", arg["main_epg_urls"])
        self.assertNotIn("ff://epg/api/xml/alive", arg["main_epg_urls"])
        self.assertEqual(arg["main_prefer_primary"], "True")
        self.assertEqual(arg["main_kr1_enabled"], "False")
        self.assertEqual(DummySetting.values["main_m3u_url"], "")
        self.assertEqual(DummySetting.values["main_epg_urls"], "")

    def test_user_specified_values_are_not_overwritten(self):
        custom_m3u = "https://example.test/channels.m3u"
        custom_epg = "https://example.test/epg.xml"
        DummySetting.values.update({"main_m3u_url": custom_m3u, "main_epg_urls": custom_epg})
        response = self.module.ModuleMain(self.fake_p).process_menu("setting", None)
        self.assertEqual(response["arg"]["main_m3u_url"], custom_m3u)
        self.assertEqual(response["arg"]["main_epg_urls"], custom_epg)

    def test_runtime_fetch_does_not_save_apikey_and_reports_source_counts(self):
        self.module.fetch_xml = self._fetch
        report = self.module._generate()
        self.assertEqual(report["전체채널"], 1)
        self.assertEqual(report["편성표연결"], 1)
        self.assertEqual(report["연결진단"]["M3U채널"], 1)
        self.assertEqual(len(report["연결진단"]["XMLTV공급원"]), 1)
        self.assertEqual(len(report["수집실패"]), 0)
        self.assertEqual(report["채널목록진단"]["모드"], "ALive 폴백")
        self.assertIn("IProxy실패유형", report["채널목록진단"])
        self.assertEqual(DummySetting.values["main_m3u_url"], "")
        self.assertEqual(DummySetting.values["main_epg_urls"], "")
        self.assertNotIn("RUNTIME_TEST", repr(report))
        output = Path(self.tmp.name) / "epgcustom"
        self.assertTrue((output / "epgall.xml").is_file())
        self.assertEqual(len(ET.parse(output / "epgall.xml").getroot().findall("programme")), 1)
        self.assertTrue((output / "report.json").is_file())

    def test_missing_m3u_channels_fails_before_xmltv(self):
        self.module.fetch_xml = lambda url: b"#EXTM3U"
        with self.assertRaisesRegex(ValueError, "M3U"):
            self.module._generate()
        self.assertEqual(DummySetting.values["main_m3u_url"], "")
        self.assertFalse((Path(self.tmp.name) / "epgcustom" / "epgall.xml").exists())

    def test_status_api_separates_current_failure_from_last_good_report(self):
        import json
        report_dir = Path(self.tmp.name) / "epgcustom"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.json").write_text(
            json.dumps({"편성표연결": 49}, ensure_ascii=False), encoding="utf-8")
        DummySetting.values.update({
            "main_status": "실패",
            "main_last_error": "ValueError",
            "main_last_run": "2026-10-14 10:00",
        })
        reply = self.module.ModuleMain(self.fake_p).process_api("status", None)
        self.assertEqual(reply["상태"], "실패")
        self.assertEqual(reply["마지막오류"], "ValueError")
        self.assertEqual(reply["생성보고서"]["편성표연결"], 49)

    def test_failure_does_not_expose_private_url(self):
        self.module._generate = lambda: (_ for _ in ()).throw(
            ValueError("https://example.test/path?apikey=FAKE_SECRET")
        )
        self.module._run_safe()
        self.assertEqual(DummySetting.values["main_status"], "실패")
        self.assertEqual(DummySetting.values["main_last_error"], "ValueError")
        self.assertNotIn("FAKE_SECRET", repr(DummySetting.values))

    def test_hybrid_channel_mode_generates_native_only_ids(self):
        raw_fetch = self._fetch
        def mock_fetch(url):
            if "/ff_iproxy2/api/m3u?type=mpegts&apikey=" in url:
                return b'#EXTM3U\n#EXTINF:-1 tvg-name="YTN",YTN\nhttps://example.invalid/ytn\n'
            return raw_fetch(url)
        self.module.fetch_xml = mock_fetch
        report = self.module._generate()
        self.assertEqual(report["전체채널"], 2)
        self.assertEqual(report["편성표연결"], 1)
        self.assertEqual(report["채널목록진단"]["모드"], "Shyni hybrid 호환")
        self.assertEqual(report["채널목록진단"]["IProxy추가채널"], 1)
        self.assertIn("hybrid 추가 1개", DummySetting.values["main_last_summary"])

    def test_hybrid_disabled_leaves_alive_channels_unchanged(self):
        DummySetting.values["main_hybrid_compatible"] = "False"
        self.module.fetch_xml = self._fetch
        report = self.module._generate()
        self.assertEqual(report["전체채널"], 1)
        self.assertEqual(report["채널목록진단"]["모드"], "지정 M3U")
        self.assertFalse(any("/ff_iproxy2/" in url for url in self.url_reads))


    def _two_channel_sources(self, broken_kr1=False):
        from service.sources import KR1_EPG_URL
        joined = (M3U + '#EXTINF:-1 tvg-id="MBC",MBC\n'
                  'https://example.invalid/mbc\n').encode()
        extra = (b'<tv><channel id="MBC.kr"><display-name>MBC</display-name></channel>'
                 b'<programme channel="MBC.kr" start="20261014090000 +0900" '
                 b'stop="20261014110000 +0900"><title>MBC live</title></programme></tv>')
        def mock_fetch(url):
            if url.endswith("/alive/api/m3u?apikey=RUNTIME_TEST"):
                return joined
            if url.endswith("/myepg/api/epgall?apikey=RUNTIME_TEST"):
                return XMLTV
            if url == KR1_EPG_URL:
                if broken_kr1:
                    raise OSError("KR1 network failure")
                return extra
            raise ValueError("unrecognized test URL")
        return mock_fetch

    def test_kr1_adds_missing_channel_without_replacing_myepg(self):
        DummySetting.values.update({
            "main_kr1_enabled": "True",
            "main_hybrid_compatible": "False",
        })
        self.module.fetch_xml = self._two_channel_sources()
        report = self.module._generate()
        self.assertEqual(report["전체채널"], 2)
        self.assertEqual(report["편성표연결"], 2)
        self.assertEqual(report["공급원별연결"], {"MyEPG": 1, "KR1": 1})
        self.assertEqual(report["공급원정책"]["KR1연동"], True)
        self.assertEqual(report["공급원정책"]["MyEPG우선"], True)
        self.assertEqual(DummySetting.values["main_epg_urls"], "")

    def test_failed_secondary_keeps_both_last_good_files(self):
        DummySetting.values.update({
            "main_kr1_enabled": "True",
            "main_hybrid_compatible": "False",
        })
        output = Path(self.tmp.name) / "epgcustom"
        self.module.fetch_xml = self._two_channel_sources()
        self.module._run_safe()
        self.assertEqual(DummySetting.values["main_status"], "정상")
        xml_before = (output / "epgall.xml").read_bytes()
        report_before = (output / "report.json").read_bytes()
        success_at = DummySetting.values["main_last_run"]

        self.module.fetch_xml = self._two_channel_sources(broken_kr1=True)
        self.module._run_safe()
        self.assertEqual(DummySetting.values["main_status"], "실패")
        self.assertIn("유지", DummySetting.values["main_last_error"])
        self.assertEqual((output / "epgall.xml").read_bytes(), xml_before)
        self.assertEqual((output / "report.json").read_bytes(), report_before)
        self.assertEqual(DummySetting.values["main_last_run"], success_at)

    def test_no_previous_file_allows_partial_success(self):
        DummySetting.values.update({
            "main_kr1_enabled": "True",
            "main_hybrid_compatible": "False",
        })
        self.module.fetch_xml = self._two_channel_sources(broken_kr1=True)
        self.module._run_safe()
        output = Path(self.tmp.name) / "epgcustom"
        self.assertEqual(DummySetting.values["main_status"], "부분 성공")
        self.assertTrue((output / "epgall.xml").is_file())
        report = __import__("json").loads((output / "report.json").read_text())
        self.assertEqual(report["편성표연결"], 1)
        self.assertEqual(report["수집실패"][0]["공급원"], "KR1")

    def test_kr1_off_does_not_fetch_third_party(self):
        DummySetting.values.update({
            "main_kr1_enabled": "False",
            "main_hybrid_compatible": "False",
        })
        self.module.fetch_xml = self._fetch
        result = self.module._generate()
        self.assertEqual(result["공급원정책"]["KR1연동"], False)
        self.assertEqual(result["편성표연결"], 1)
        self.assertFalse(any("epgshare01.online" in x for x in self.url_reads))



    def test_verified_aliases_apply_and_user_override_can_disable(self):
        from service.sources import KR1_EPG_URL
        DummySetting.values.update({
            "main_kr1_enabled": "True",
            "main_hybrid_compatible": "False",
        })
        m3u = (M3U + '#EXTINF:-1 tvg-id="TV CHOSUN",TV CHOSUN\n'
               'https://example.invalid/tvchosun\n'
               '#EXTINF:-1 tvg-id="ANIMAX",ANIMAX\n'
               'https://example.invalid/animax\n').encode()
        kr1 = (b'<tv>'
               b'<channel id="TVchosun.kr"><display-name>TV\xec\xa1\xb0\xec\x84\xa0</display-name></channel>'
               b'<channel id="animax.kr"><display-name>\xec\x95\xa0\xeb\x8b\x88\xeb\xa7\xa5\xec\x8a\xa4</display-name></channel>'
               b'<programme channel="TVchosun.kr" start="20261014090000 +0900" '
               b'stop="20261014110000 +0900"><title>TV schedule</title></programme>'
               b'<programme channel="animax.kr" start="20261014090000 +0900" '
               b'stop="20261014110000 +0900"><title>Anime</title></programme></tv>')
        def mock_fetch(url):
            if url.endswith("/alive/api/m3u?apikey=RUNTIME_TEST"):
                return m3u
            if url.endswith("/myepg/api/epgall?apikey=RUNTIME_TEST"):
                return XMLTV
            if url == KR1_EPG_URL:
                return kr1
            raise ValueError("unexpected URL")
        self.module.fetch_xml = mock_fetch
        report = self.module._generate()
        self.assertEqual(report["편성표연결"], 3)
        self.assertEqual(report["공급원별연결"], {"MyEPG": 1, "KR1": 2})

        DummySetting.values["main_aliases_json"] = '{"ANIMAX": []}'
        report2 = self.module._generate()
        self.assertEqual(report2["편성표연결"], 2)
        self.assertIn("ANIMAX", {x["ID"] for x in report2["미연결채널"]})



    def test_diagnostics_menu_loads_safely_before_first_generation(self):
        reply = self.module.ModuleMain(self.fake_p).process_menu("diagnostics", None)
        self.assertEqual(reply["template"], "epgcustom_main_diagnostics.html")
        self.assertEqual(reply["arg"]["rows"], [])
        self.assertIn("없습니다", reply["arg"]["report_error"])

    def test_diagnostics_menu_accepts_old_v03_report(self):
        import json
        report_dir = Path(self.tmp.name) / "epgcustom"
        report_dir.mkdir(parents=True, exist_ok=True)
        old = {
            "전체채널": 2, "편성표연결": 1, "편성표미연결": 1,
            "채널별상태": [
                {"ID": "KBS1", "이름": "KBS1", "연결": True,
                 "공급원": "MyEPG", "편성항목": 48},
                {"ID": "EBS2", "이름": "EBS2", "연결": False},
            ],
        }
        (report_dir / "report.json").write_text(
            json.dumps(old, ensure_ascii=False), encoding="utf-8")
        reply = self.module.ModuleMain(self.fake_p).process_menu("diagnostics", None)
        self.assertFalse(reply["arg"]["detailed"])
        self.assertEqual(reply["arg"]["connected"], 1)
        self.assertEqual(reply["arg"]["unconnected"], 1)
        self.assertEqual(reply["arg"]["rows"][1]["미연결사유"],
                         "이전 보고서: 재생성 필요")

    def test_diagnostics_menu_shows_last_good_report_during_failure(self):
        import json
        report_dir = Path(self.tmp.name) / "epgcustom"
        report_dir.mkdir(parents=True, exist_ok=True)
        new = {
            "전체채널": 1, "편성표연결": 1, "편성표미연결": 0,
            "채널별상태": [
                {"ID": "MBC", "이름": "MBC", "연결": True,
                 "공급원": "KR1", "편성항목": 83,
                 "원본채널ID": "mbc.kr", "매칭방식": "이름정확"},
            ],
            "진단요약": {"연결": 1, "미연결": 0},
            "중복매핑": [],
        }
        (report_dir / "report.json").write_text(
            json.dumps(new, ensure_ascii=False), encoding="utf-8")
        DummySetting.values["main_status"] = "실패"
        DummySetting.values["main_last_error"] = "KR1 일시 장애"
        reply = self.module.ModuleMain(self.fake_p).process_menu("diagnostics", None)
        self.assertEqual(reply["arg"]["current_status"], "실패")
        self.assertEqual(reply["arg"]["current_error"], "KR1 일시 장애")
        self.assertTrue(reply["arg"]["detailed"])
        self.assertEqual(reply["arg"]["rows"][0]["원본채널ID"], "mbc.kr")

    def test_status_api_gracefully_handles_corrupt_report(self):
        report_dir = Path(self.tmp.name) / "epgcustom"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.json").write_bytes(b'<<incorrect json>>')
        reply = self.module.ModuleMain(self.fake_p).process_api("status", None)
        self.assertIsNone(reply["생성보고서"])
        self.assertTrue(reply["보고서오류"])



if __name__ == "__main__":
    unittest.main()
