"""Shyni hybrid의 M3U 조합 규칙과 EPG 채널 식별자 회귀 테스트."""
import unittest

from service.core import parse_m3u
from service.hybrid import merge_shyni_hybrid


ALIVE = """#EXTM3U
#EXTINF:-1 tvg-id="KBS1" tvg-name="KBS1",KBS1
https://ff.example/kbs1
#EXTINF:-1 tvg-id="KBS 1TV" tvg-name="KBS 1TV",KBS 1TV
https://ff.example/duplicate-kbs1
#EXTINF:-1 tvg-id="KBS2" tvg-name="KBS2",KBS2
https://ff.example/kbs2
#EXTINF:-1 tvg-id="KBS 2TV",KBS 2TV
https://ff.example/duplicate-kbs2
#EXTINF:-1 tvg-id="MBC" tvg-name="MBC",MBC
https://ff.example/mbc
#EXTINF:-1 tvg-id="EBS 2" tvg-name="EBS 2",EBS 2
https://ff.example/ebs2
#EXTINF:-1 tvg-id="SBS",SBS
https://ff.example/sbs
"""
IPROXY = """#EXTM3U
#EXTINF:-1 tvg-name="KBS1",KBS1
https://ff.example/iproxy/kbs1
#EXTINF:-1 tvg-name="MBC",MBC
https://ff.example/iproxy/mbc
#EXTINF:-1 tvg-name="EBS2",EBS2
https://ff.example/iproxy/ebs2
#EXTINF:-1 tvg-name="UXN",UXN
https://ff.example/iproxy/uxn
#EXTINF:-1 tvg-name="UXN",UXN
https://ff.example/iproxy/uxn-duplicate
"""


class HybridPlaylistTests(unittest.TestCase):
    def test_merges_sources_like_shyni_and_removes_only_kbs_duplicates(self):
        merged, diag = merge_shyni_hybrid(ALIVE, IPROXY)
        channels = parse_m3u(merged)
        ids = {channel["id"] for channel in channels}
        self.assertEqual(ids, {"KBS1", "KBS2", "MBC", "EBS 2", "SBS", "EBS2", "UXN"})
        self.assertEqual(diag["IProxy추가채널"], 2)
        self.assertEqual(diag["중복KBS제외"], 2)
        self.assertEqual(diag["최종채널ID"], 7)
        self.assertEqual(diag["모드"], "Shyni hybrid 호환")

    def test_zero_extra_native_channels_valid(self):
        only_dup = '#EXTM3U\n#EXTINF:-1 tvg-name="MBC",MBC\nhttps://example/mbc\n'
        merged, diag = merge_shyni_hybrid(ALIVE, only_dup)
        self.assertEqual(diag["IProxy추가채널"], 0)
        self.assertEqual(diag["최종채널ID"], 5)

    def test_invalid_or_empty_iproxy_rejected_for_safe_fallback(self):
        with self.assertRaises(ValueError):
            merge_shyni_hybrid(ALIVE, "#EXTM3U")
        with self.assertRaises(ValueError):
            merge_shyni_hybrid("#EXTM3U", IPROXY)

    def test_input_urls_remain_internal_to_m3u_generation_only(self):
        merged, _ = merge_shyni_hybrid(ALIVE, IPROXY)
        self.assertIn(b"#EXTINF:-1 tvg-name=\"UXN\",UXN", merged)
        self.assertIn(b"https://ff.example/iproxy/uxn", merged)


if __name__ == "__main__":
    unittest.main()
