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
        DummySetting.values = {"main_m3u_url": "", "main_epg_urls": "", "main_aliases_json": "{}"}
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
            make_apikey_url=lambda path: "https://ff.example.test" + path + "?apikey=RUNTIME_TEST"
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
        self.assertIn("ff://epg/api/xml/alive", arg["main_epg_urls"])
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
        self.assertEqual(len(report["수집실패"]), 1)
        self.assertEqual(report["수집실패"][0]["공급원"], "공급원2")
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


if __name__ == "__main__":
    unittest.main()
