"""실제 XMLTV 시간 형식, 공급원 품질, 채널명 충돌 검증."""
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from service.core import xmltv_time, build_epg

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=KST)
M3U = '#EXTM3U\n#EXTINF:-1 tvg-id="MBC",MBC\nhttps://example.invalid/mbc\n'


def make_xml(programs, name="MBC", cid="mbc-main"):
    lines = ['<tv>', f'<channel id="{cid}"><display-name>{name}</display-name></channel>']
    for start, stop, title in programs:
        lines.append(
            f'<programme channel="{cid}" start="{start}" stop="{stop}">'
            f'<title>{title}</title></programme>'
        )
    lines.append('</tv>')
    return ''.join(lines).encode()


def records(n):
    data = []
    for i in range(n):
        a = NOW + timedelta(minutes=30*i)
        b = a + timedelta(minutes=30)
        data.append((a.strftime('%Y%m%d%H%M%S +0900'),
                     b.strftime('%Y%m%d%H%M%S +0900'),f'방송 {i}'))
    return data


class GuideQualityTests(unittest.TestCase):
    def test_xmltv_seconds_are_preserved(self):
        dt = xmltv_time('20261014123456 +0900')
        self.assertEqual((dt.hour, dt.minute, dt.second), (12, 34, 56))

    def test_xmltv_minutes_only_and_timezone(self):
        dt = xmltv_time('202610141234 +0900')
        self.assertEqual((dt.hour, dt.minute, dt.second), (12, 34, 0))
        dt2 = xmltv_time('20261014123456 +0000')
        self.assertEqual(dt2.astimezone(KST).hour, 21)

    def test_trailing_garbage_rejected(self):
        self.assertIsNone(xmltv_time('20261014123456 +0900 GARBAGE'))
        self.assertIsNone(xmltv_time('20261014123456 GARBAGE'))

    def test_source_priority_with_similar_coverage(self):
        first = make_xml(records(4))
        second = make_xml(records(5))
        _,report=build_epg(M3U,[('MyEPG',first),('FF EPG',second)],now=NOW)
        self.assertEqual(report['공급원별연결']['MyEPG'],1)
        self.assertEqual(report['편성항목'],4)

    def test_significantly_better_guide_source_is_selected(self):
        first=make_xml(records(1))
        second=make_xml(records(6))
        xml,report=build_epg(M3U,[('MyEPG',first),('FF EPG',second)],now=NOW)
        self.assertEqual(report['공급원별연결']['FF EPG'],1)
        self.assertEqual(len(ET.fromstring(xml).findall('programme')),6)

    def test_other_mbc_channel_is_not_mapped(self):
        other=make_xml(records(5),name='MBC 뉴스',cid='mbc-news')
        _,report=build_epg(M3U,[('MyEPG',other)],now=NOW)
        self.assertEqual(report['편성표연결'],0)
        self.assertEqual(report['미연결채널'][0]['이름'],'MBC')


if __name__ == '__main__':
    unittest.main()
