"""기본 공급원·사용자 설정 보존·실행 시 인증 해석 회귀 테스트."""
import unittest

from service.sources import (
    DEFAULT_M3U, DEFAULT_EPGS, epg_settings, epg_setting_display,
    m3u_setting, source_url,
)


class SourceDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def make_ff_url(path):
            self.calls.append(path)
            return "https://ff.example.test" + path + ("&" if "?" in path else "?") + "apikey=RUNTIME_ONLY"
        self.builder = make_ff_url

    def test_m3u_empty_uses_alive_default(self):
        self.assertEqual(m3u_setting(""), DEFAULT_M3U)
        self.assertEqual(m3u_setting(None), DEFAULT_M3U)
        self.assertEqual(DEFAULT_M3U, "ff://alive/api/m3u")

    def test_xmltv_empty_uses_priority_order(self):
        self.assertEqual(epg_settings(""), list(DEFAULT_EPGS))
        self.assertEqual(epg_settings(None), list(DEFAULT_EPGS))
        self.assertEqual(epg_setting_display(""), "ff://myepg/api/epgall")

    def test_legacy_auto_sources_drop_synology_404(self):
        old = "ff://myepg/api/epgall\nff://epg/api/xml/alive"
        self.assertEqual(epg_settings(old), ["ff://myepg/api/epgall"])
        self.assertEqual(epg_setting_display(old), "ff://myepg/api/epgall")

    def test_iproxy_uses_expected_media_type(self):
        self.assertEqual(
            source_url("ff://ff_iproxy2/api/m3u", self.builder),
            "https://ff.example.test/ff_iproxy2/api/m3u?type=mpegts&apikey=RUNTIME_ONLY"
        )
        self.assertEqual(self.calls, ["/ff_iproxy2/api/m3u?type=mpegts"])

    def test_custom_user_values_preserved(self):
        custom_m3u = "https://custom.example.test/hybrid/api/m3u?key=abc"
        custom_epg = "https://custom.example.test/guide.xml\n# comment\nhttps://backup.example.test/epg"
        self.assertEqual(m3u_setting(custom_m3u), custom_m3u)
        self.assertEqual(
            epg_settings(custom_epg),
            ["https://custom.example.test/guide.xml", "https://backup.example.test/epg"],
        )

    def test_default_resolution_uses_ff_runtime_auth_only(self):
        result = source_url(m3u_setting(""), self.builder)
        self.assertEqual(result, "https://ff.example.test/alive/api/m3u?apikey=RUNTIME_ONLY")
        self.assertEqual(self.calls, ["/alive/api/m3u"])
        self.assertNotIn("RUNTIME_ONLY", DEFAULT_M3U)

    def test_both_epgs_resolve_with_ff_runtime(self):
        values = [source_url(src, self.builder) for src in epg_settings("")]
        self.assertEqual(
            self.calls,
            ["/myepg/api/epgall"],
        )
        self.assertEqual(len(values), 1)
        self.assertTrue(all("RUNTIME_ONLY" in value for value in values))

    def test_explicit_url_unmodified_and_no_ff_auth(self):
        custom = "https://my.example.test/hybrid/api/m3u?apikey=custom"
        self.assertEqual(source_url(custom, self.builder), custom)
        self.assertEqual(self.calls, [])

    def test_invalid_or_unknown_alias_rejected(self):
        for src in ("ff://untrusted/api", "", "file:///etc/passwd", "http://", "/alive/api/m3u"):
            with self.subTest(src=src):
                with self.assertRaises(ValueError):
                    source_url(src, self.builder)

    def test_embedded_username_password_rejected(self):
        with self.assertRaises(ValueError):
            source_url("https://user:password@host.test/feed.xml", self.builder)

    def test_old_blank_settings_are_not_mutated(self):
        old = {"main_m3u_url": "", "main_epg_urls": ""}
        display = {
            "main_m3u_url": m3u_setting(old["main_m3u_url"]),
            "main_epg_urls": epg_setting_display(old["main_epg_urls"]),
        }
        self.assertEqual(old["main_m3u_url"], "")
        self.assertEqual(old["main_epg_urls"], "")
        self.assertIn("ff://", display["main_epg_urls"])


if __name__ == "__main__":
    unittest.main()
