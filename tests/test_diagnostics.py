"""EPGCustom 4차 채널 진단과 원본 공유 XML 복사에 대한 회귀 테스트."""
from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import DictLoader, Environment, select_autoescape

from service.core import build_epg
from service.diagnostics import (
    MAX_REPORT_BYTES, load_report, prepare_diagnostics_view, summarize_diagnostics,
)

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=timezone(timedelta(hours=9)))
START = "20261014090000 +0900"
STOP = "20261014110000 +0900"


def m3u(*ids: str) -> bytes:
    return (
        "#EXTM3U\n" +
        "".join(f'#EXTINF:-1 tvg-id="{cid}",{cid}\nhttps://example.invalid/stream\n'
                for cid in ids)
    ).encode()


def xmltv(*sources: tuple[str, str, str]) -> bytes:
    """(source id, display name, time mode)."""
    parts = ["<tv>"]
    for sid, name, mode in sources:
        parts.append(f'<channel id="{sid}"><display-name>{name}</display-name></channel>')
        if mode == "empty":
            continue
        if mode == "old":
            start, stop = "20260114090000 +0900", "20260114110000 +0900"
        elif mode == "invalid":
            start, stop = "2026BADDATE", "20261014110000 +0900"
        else:
            start, stop = START, STOP
        parts.append(f'<programme channel="{sid}" start="{start}" stop="{stop}">'
                     f'<title>{name} guide</title></programme>')
    return "".join(parts + ["</tv>"]).encode()


class DiagnosticReportTests(unittest.TestCase):
    def test_correct_connected_source_and_match_mode(self):
        _, report = build_epg(
            m3u("MBC", "KBS 1"), [("MyEPG", xmltv(("mbc.kr", "MBC", "valid"),
                                                 ("KBS 1", "KBS 1", "valid")))],
            now=NOW)
        items = {row["ID"]: row for row in report["채널별상태"]}
        self.assertEqual(items["MBC"]["원본채널ID"], "mbc.kr")
        self.assertEqual(items["MBC"]["매칭방식"], "이름정확")
        self.assertEqual(items["KBS 1"]["매칭방식"], "ID정확")
        self.assertEqual(report["진단요약"]["연결"], 2)
        self.assertEqual(report["중복매핑"], [])

    def test_verified_alias_is_not_reported_as_error(self):
        _, report = build_epg(
            m3u("TV CHOSUN"), [("KR1", xmltv(("c1", "TV조선", "valid")))],
            aliases={"TV CHOSUN": ["TV조선"]}, now=NOW)
        row = report["채널별상태"][0]
        self.assertTrue(row["연결"])
        self.assertEqual(row["매칭방식"], "별칭정확")
        self.assertFalse(row["매핑공유"])
        self.assertEqual(report["중복매핑"], [])

    def test_no_channel_in_feed_reason(self):
        _, report = build_epg(
            m3u("EBS 2"), [("KR1", xmltv(("ebs-plus-2", "EBS 플러스2", "valid")))], now=NOW)
        self.assertEqual(report["채널별상태"][0]["미연결사유"], "원본채널없음")

    def test_channel_metadata_but_no_programmes_reason(self):
        _, report = build_epg(
            m3u("MBC"), [("KR1", xmltv(("m1", "MBC", "empty"),
                                      ("other", "Other", "valid")))], now=NOW)
        self.assertEqual(report["채널별상태"][0]["미연결사유"], "원본편성없음")

    def test_channel_programmes_only_outside_window_reason(self):
        _, report = build_epg(
            m3u("MBC"), [("KR1", xmltv(("m1", "MBC", "old")))], now=NOW)
        self.assertEqual(report["채널별상태"][0]["미연결사유"], "유효시간대편성없음")

    def test_channel_programme_invalid_time_reason(self):
        _, report = build_epg(
            m3u("MBC"), [("KR1", xmltv(("m1", "MBC", "invalid")))], now=NOW)
        self.assertEqual(report["채널별상태"][0]["미연결사유"], "원본시간오류")

    def test_ambiguous_display_names_are_not_automatically_matched(self):
        _, report = build_epg(
            m3u("MBC"), [("KR1", xmltv(("mbc-a", "MBC", "valid"),
                                      ("mbc-b", "MBC", "valid")))], now=NOW)
        self.assertEqual(report["채널별상태"][0]["미연결사유"], "매칭모호")
        self.assertEqual(report["편성표연결"], 0)

    def test_one_source_shared_between_two_ids_keeps_both_xml_programmes(self):
        source = xmltv(("shared-id", "SBS", "valid"))
        data, report = build_epg(
            m3u("SBS", "SBS HD"), [("MyEPG", source)],
            aliases={"SBS HD": ["SBS"]}, now=NOW)
        tree = ET.fromstring(data)
        output_ids = [element.get("channel") for element in tree.findall("programme")]
        self.assertEqual(output_ids, ["SBS", "SBS HD"])
        self.assertEqual(report["편성표연결"], 2)
        self.assertEqual(report["편성항목"], 2)
        self.assertEqual(report["중복매핑"][0]["원본채널ID"], "shared-id")
        self.assertEqual(report["중복매핑"][0]["대상채널ID"], ["SBS", "SBS HD"])
        self.assertEqual(report["중복매핑"][0]["판정"], "검토")
        self.assertEqual(report["진단요약"]["원본공유대상채널"], 2)
        self.assertTrue(all(row["매핑공유"] for row in report["채널별상태"]))

    def test_matching_source_id_but_different_provider_not_shared(self):
        _, report = build_epg(
            m3u("MBC", "SBS"),
            [("MyEPG", xmltv(("X", "MBC", "valid"))),
             ("KR1", xmltv(("X", "SBS", "valid")))],
            now=NOW)
        self.assertEqual(report["편성표연결"], 2)
        self.assertEqual(report["중복매핑"], [])

    def test_reason_summary_counts(self):
        _, report = build_epg(m3u("MBC", "EBS2"),
                              [("KR1", xmltv(("mbc.kr", "MBC", "old")))], now=NOW)
        self.assertEqual(report["진단요약"]["미연결사유별"],
                         {"원본채널없음": 1, "유효시간대편성없음": 1})
        self.assertEqual(report["편성표미연결"], 2)


class DiagnosticFileAndViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.report_file = Path(self.tmp.name) / "report.json"

    def test_missing_report_is_safe(self):
        data, err = load_report(self.report_file)
        self.assertIsNone(data)
        self.assertIn("없습니다", err)
        view = prepare_diagnostics_view(None)
        self.assertEqual(view["rows"], [])
        self.assertFalse(view["detailed"])

    def test_corrupt_or_non_object_json_is_safe(self):
        for data in (b"<html>", b"[]", b"\xff"):
            with self.subTest(data=data):
                self.report_file.write_bytes(data)
                report, error = load_report(self.report_file)
                self.assertIsNone(report)
                self.assertTrue(error)

    def test_oversized_report_is_rejected(self):
        self.report_file.write_bytes(b"0" * (MAX_REPORT_BYTES + 1))
        report, error = load_report(self.report_file)
        self.assertIsNone(report)
        self.assertIn("크기", error)

    def test_roundtrip_new_report_and_old_report_fallback(self):
        report = {
            "전체채널": 2, "편성표연결": 1, "편성표미연결": 1,
            "생성시각": "2026-10-14T15:00:00+09:00",
            "채널별상태": [
                {"ID": "MBC", "이름": "MBC", "연결": True,
                 "공급원": "KR1", "편성항목": 70, "원본채널ID": "MBC.kr"},
                {"ID": "EBS2", "이름": "EBS2", "연결": False}
            ],
        }
        self.report_file.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        data, error = load_report(self.report_file)
        self.assertFalse(error)
        old = prepare_diagnostics_view(data)
        self.assertEqual(old["rows"][1]["미연결사유"], "이전 보고서: 재생성 필요")
        self.assertFalse(old["detailed"])
        summarize_diagnostics(data)
        new = prepare_diagnostics_view(data)
        self.assertTrue(new["detailed"])
        self.assertEqual(new["rows"][1]["미연결사유"], "미확인")

    def test_bounded_rows_and_untrusted_text_escaped_in_html(self):
        malicious = '<img src=x onerror="alert(1)">'
        data = {
            "전체채널": 1, "편성표연결": 0, "편성표미연결": 1,
            "채널별상태": [{"ID": malicious, "이름": malicious, "연결": False,
                         "미연결사유": "원본채널없음"}],
            "진단요약": {},
        }
        view = prepare_diagnostics_view(data)
        view.update({"current_status": "정상", "current_error": "", "report_error": ""})
        template = (Path(__file__).resolve().parents[1] /
                    "templates/epgcustom_main_diagnostics.html").read_text(encoding="utf-8")
        env = Environment(
            loader=DictLoader({
                "base.html": "{% block content %}{% endblock %}",
                "epgcustom_main_diagnostics.html": template,
            }), autoescape=select_autoescape(["html"]))
        html = env.get_template("epgcustom_main_diagnostics.html").render(arg=view)
        self.assertNotIn(malicious, html)
        self.assertIn("&lt;img", html)
        self.assertIn('data-reason="원본채널없음"', html)
        self.assertIn("epg-diag-search", html)
        self.assertIn("원본 공유", html)


if __name__ == "__main__":
    unittest.main()
