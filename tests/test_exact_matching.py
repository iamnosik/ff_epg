"""채널명 충돌과 검증된 별칭/공급원 우선순위를 확인하는 독립 회귀 테스트."""
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from service.core import build_epg, normalize_name


NOW = datetime(2026, 10, 14, 10, 0, tzinfo=timezone(timedelta(hours=9)))
START = "20261014093000 +0900"
STOP = "20261014110000 +0900"


def playlist(*names):
    lines = ["#EXTM3U"]
    for name in names:
        lines.extend([f'#EXTINF:-1 tvg-id="{name}",{name}',
                      'https://example.invalid/stream'])
    return "\n".join(lines)


def xml_for(*channels):
    data = ['<tv>']
    for ident, name in channels:
        data.append(f'<channel id="{ident}"><display-name>{name}</display-name></channel>')
        data.append(
            f'<programme channel="{ident}" start="{START}" stop="{STOP}">'
            f'<title>{name} programme</title></programme>')
    return ''.join(data + ['</tv>']).encode()


class ExactChannelMatchingTests(unittest.TestCase):
    def test_plus_suffix_is_significant(self):
        self.assertNotEqual(normalize_name("SPOTV Prime"), normalize_name("SPOTV Prime+"))
        self.assertNotEqual(normalize_name("홈&쇼핑"), normalize_name("홈쇼핑"))

    def test_prime_and_prime_plus_remain_different(self):
        m3u = playlist("SPOTV Prime", "SPOTV Prime+")
        guide = xml_for(("136.sk", "SPOTV Prime"), ("139.sk", "SPOTV Prime+"))
        xml, report = build_epg(m3u, [("MyEPG", guide)], now=NOW)
        self.assertEqual(report["편성표연결"], 2)
        programmes = ET.fromstring(xml).findall("programme")
        self.assertEqual({p.get("channel") for p in programmes},
                         {"SPOTV Prime", "SPOTV Prime+"})
        for item in programmes:
            self.assertEqual(item.get("channel") + " programme",
                             item.findtext("title"))

    def test_prime_is_not_prime_plus_fallback(self):
        _, report = build_epg(
            playlist("SPOTV Prime+"),
            [("MyEPG", xml_for(("136.sk", "SPOTV Prime")))], now=NOW)
        self.assertEqual(report["편성표연결"], 0)

    def test_exact_name_before_normalized_alias(self):
        guide = xml_for(("136.sk", "SPOTV Prime"), ("139.sk", "SPOTV Prime+"))
        _, report = build_epg(
            playlist("SPOTV Prime+"), [("MyEPG", guide)], now=NOW,
            aliases={"SPOTV Prime+": ["SPOTV Prime"]})
        self.assertEqual(report["편성표연결"], 1)
        self.assertEqual(report["편성항목"], 1)

    def test_tv_chosun_and_animax_require_verified_aliases(self):
        feed = xml_for(("TV조선.kr", "TV조선"), ("애니맥스.kr", "애니맥스"))
        m3u = playlist("TV CHOSUN", "ANIMAX")
        _, without = build_epg(m3u, [("KR1", feed)], now=NOW)
        self.assertEqual(without["편성표연결"], 0)
        _, with_alias = build_epg(
            m3u, [("KR1", feed)], now=NOW,
            aliases={"TV CHOSUN": ["TV조선"], "ANIMAX": ["애니맥스"]})
        self.assertEqual(with_alias["편성표연결"], 2)

    def test_stale_myepg_falls_back_to_fresh_kr1(self):
        stale = xml_for(("MBC-OLD", "MBC")).replace(b"20261014", b"20260114")
        fresh = xml_for(("MBC.kr", "MBC"))
        _, report = build_epg(
            playlist("MBC"), [("MyEPG", stale), ("KR1", fresh)], now=NOW,
            prefer_primary=True)
        self.assertEqual(report["공급원별연결"], {"MyEPG": 0, "KR1": 1})

    def test_myepg_kept_when_second_provider_has_more_programmes(self):
        short = xml_for(("MBC-ORIGINAL", "MBC"))
        more = xml_for(("MBC.kr", "MBC"))
        more = more.replace(
            b'</tv>',
            f'<programme channel="MBC.kr" start="20261014110000 +0900" stop="20261014123000 +0900"><title>next</title></programme></tv>'.encode()
        )
        _, report = build_epg(
            playlist("MBC"), [("MyEPG", short), ("KR1", more)], now=NOW,
            prefer_primary=True)
        self.assertEqual(report["공급원별연결"], {"MyEPG": 1, "KR1": 0})
        self.assertEqual(report["편성항목"], 1)

    def test_opt_out_can_choose_longer_provider(self):
        short = xml_for(("MBC-ORIGINAL", "MBC"))
        more = xml_for(("MBC.kr", "MBC")).replace(
            b'</tv>',
            b'<programme channel="MBC.kr" start="20261014110000 +0900" stop="20261014180000 +0900"><title>more</title></programme></tv>'
        )
        _, report = build_epg(
            playlist("MBC"), [("MyEPG", short), ("KR1", more)], now=NOW,
            prefer_primary=False)
        self.assertEqual(report["공급원별연결"], {"MyEPG": 0, "KR1": 1})


if __name__ == "__main__":
    unittest.main()
