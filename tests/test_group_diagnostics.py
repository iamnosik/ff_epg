"""v0.5.0 그룹별 EPG 연결 진단 및 FF 화면 회귀 검증."""
import unittest
from pathlib import Path
from jinja2 import DictLoader, Environment, select_autoescape
from service.diagnostics import summarize_diagnostics, summarize_groups, prepare_diagnostics_view


class GroupDiagnosticTests(unittest.TestCase):
    def test_counts_are_unique_target_channels_and_sort_missing_first(self):
        entries = [
            {"ID": "MBC", "그룹": "지상파", "연결": True},
            {"ID": "EBS2", "그룹": "지상파", "연결": False, "미연결사유": "원본채널없음"},
            {"ID": "W1", "그룹": "웨이브", "연결": False, "미연결사유": "원본채널없음"},
            {"ID": "W2", "그룹": "웨이브", "연결": False, "미연결사유": "원본편성없음"},
            {"ID": "W3", "그룹": "웨이브", "연결": True},
            {"ID": "X1", "그룹": "", "연결": False},
        ]
        groups = summarize_groups(entries)
        self.assertEqual([g["그룹"] for g in groups], ["웨이브", "지상파", "그룹 없음"])
        self.assertEqual(groups[0]["전체"], 3)
        self.assertEqual(groups[0]["연결"], 1)
        self.assertEqual(groups[0]["미연결"], 2)
        self.assertEqual(groups[0]["연결률"], 33.3)
        self.assertEqual(groups[0]["미연결사유별"],
                         {"원본채널없음": 1, "원본편성없음": 1})
        self.assertEqual(groups[2]["미연결사유별"], {"미확인": 1})

    def test_group_report_and_old_04_json_compatibility(self):
        report = {
            "전체채널": 3, "편성표연결": 1, "편성표미연결": 2,
            "채널별상태": [
                {"ID": "EBS 1", "이름": "EBS 1", "그룹": "지상파", "연결": True},
                {"ID": "EBS2", "이름": "EBS2", "그룹": "지상파", "연결": False,
                 "미연결사유": "원본채널없음"},
                {"ID": "SBS No.1", "이름": "SBS No.1", "그룹": "웨이브", "연결": False,
                 "미연결사유": "원본채널없음"},
            ],
            "진단요약": {"연결": 1, "미연결": 2},
        }
        old_view = prepare_diagnostics_view(report)
        self.assertEqual(old_view["groups"], ["웨이브", "지상파"])
        self.assertEqual(old_view["group_summary"][0]["미연결"], 1)
        self.assertEqual(len(old_view["top_missing_groups"]), 2)
        self.assertEqual(old_view["rows"][0]["그룹표시"], "지상파")
        summarize_diagnostics(report)
        self.assertEqual(report["그룹별요약"], summarize_groups(report["채널별상태"]))
        self.assertEqual(report["그룹별요약"][0]["전체"], 2)

    def test_group_name_html_escaped_and_filter_elements_render(self):
        malicious = '<svg onload="alert(1)">'
        report = {
            "전체채널": 1, "편성표연결": 0, "편성표미연결": 1,
            "채널별상태": [
                {"ID": "unsafe", "이름": "unsafe", "그룹": malicious,
                 "연결": False, "미연결사유": "원본채널없음"},
            ],
            "진단요약": {},
        }
        view = prepare_diagnostics_view(report)
        view.update({"current_status": "정상", "current_error": "", "report_error": ""})
        template = (Path(__file__).resolve().parents[1]
                    / "templates/epgcustom_main_diagnostics.html").read_text(encoding="utf-8")
        env = Environment(
            loader=DictLoader({"base.html": "{% block content %}{% endblock %}",
                               "epgcustom_main_diagnostics.html": template}),
            autoescape=select_autoescape(["html"]))
        html = env.get_template("epgcustom_main_diagnostics.html").render(arg=view)
        self.assertNotIn(malicious, html)
        self.assertIn("&lt;svg", html)
        self.assertIn("epg-diag-group", html)
        self.assertIn("epg-diag-group-focus", html)
        self.assertIn("data-group=", html)

    def test_group_names_not_mutated_in_source_report(self):
        report = {"채널별상태": [{"ID": "X", "그룹": "", "연결": False}]}
        view = prepare_diagnostics_view(report)
        self.assertEqual(report["채널별상태"][0]["그룹"], "")
        self.assertEqual(view["rows"][0]["그룹표시"], "그룹 없음")


if __name__ == "__main__":
    unittest.main()
