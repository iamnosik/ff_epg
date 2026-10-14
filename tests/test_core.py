"""EPGCustom 단위 회귀 테스트. FlaskFarm 설치 없이 실행 가능."""
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from service.core import build_epg, normalize_name, parse_aliases, parse_m3u

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=KST)
M3U = '''#EXTM3U
#EXTINF:-1 tvg-id="KBS1" tvg-name="KBS1" group-title="지상파",KBS1
https://example.invalid/kbs1
#EXTINF:-1 tvg-id="MBC" tvg-name="MBC" group-title="지상파",MBC
https://example.invalid/mbc
#EXTINF:-1 tvg-id="EBS 1" tvg-name="EBS 1" group-title="지상파",EBS 1
https://example.invalid/ebs1
'''
XML1 = b'''<tv><channel id="KBS-ID"><display-name>KBS1</display-name></channel>
<channel id="EBS-ID"><display-name>EBS1</display-name></channel>
<channel id="NEWS"><display-name>MBC News</display-name></channel>
<programme channel="KBS-ID" start="20261014090000 +0900" stop="20261014110000 +0900"><title>news</title></programme>
<programme channel="EBS-ID" start="20261014090000 +0900" stop="20261014110000 +0900"><title>school</title></programme>
<programme channel="NEWS" start="20261014090000 +0900" stop="20261014110000 +0900"><title>wrong news</title></programme></tv>'''
XML2 = b'''<tv><channel id="MBC-ID"><display-name>MBC</display-name></channel>
<programme channel="MBC-ID" start="20261014093000 +0900" stop="20261014103000 +0900"><title>morning</title></programme></tv>'''


class EPGTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(normalize_name('EBS 1'), normalize_name('EBS1'))
        self.assertNotEqual(normalize_name('MBC'), normalize_name('MBC News'))

    def test_m3u(self):
        self.assertEqual([c['id'] for c in parse_m3u(M3U)], ['KBS1', 'MBC', 'EBS 1'])

    def test_existing_epg_and_missing_mbc(self):
        xml, report = build_epg(M3U, [('원본1', XML1)], now=NOW)
        self.assertEqual(report['편성표연결'], 2)
        self.assertEqual(report['편성표미연결'], 1)
        self.assertEqual(report['미연결채널'][0]['이름'], 'MBC')
        self.assertEqual([p.get('channel') for p in ET.fromstring(xml).findall('programme')], ['KBS1', 'EBS 1'])

    def test_two_sources(self):
        xml, report = build_epg(M3U, [('원본1', XML1), ('원본2', XML2)], now=NOW)
        self.assertEqual(report['편성표연결'], 3)
        self.assertEqual(report['공급원별연결'], {'원본1': 2, '원본2': 1})
        self.assertEqual(len(ET.fromstring(xml).findall('programme')), 3)

    def test_old_data_falls_back(self):
        old = XML2.replace(b'20261014', b'20260114')
        xml, report = build_epg(M3U, [('지난데이터', old), ('현재데이터', XML2)], now=NOW)
        self.assertEqual(report['공급원별연결']['지난데이터'], 0)
        self.assertEqual(report['공급원별연결']['현재데이터'], 1)
        self.assertEqual(len(ET.fromstring(xml).findall('programme')), 1)

    def test_alias_validation(self):
        with self.assertRaises(ValueError):
            parse_aliases({'EBS 1': 'EBS1'})
        self.assertEqual(parse_aliases({'EBS 1': ['EBS1']}), {'EBS 1': ['EBS1']})

    def test_duplicate_programmes_are_ignored(self):
        repeated = XML2.replace(b'</tv>', XML2[XML2.find(b'<programme'):XML2.find(b'</tv>')] + b'</tv>')
        _, report = build_epg(M3U, [('원본', repeated)], now=NOW)
        self.assertEqual(report['편성항목'], 1)

    def test_empty_m3u_refused(self):
        with self.assertRaises(ValueError):
            build_epg('#EXTM3U', [('원본', XML1)], now=NOW)


if __name__ == '__main__':
    unittest.main()
