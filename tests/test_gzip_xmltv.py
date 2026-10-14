"""압축 XMLTV 다운로드/해제 제한 검증 (네트워크 사용 없음)."""
import gzip
import io
import unittest
from unittest.mock import patch

from service.io import decode_xmltv_content, fetch_xml


class FakeResponse(io.BytesIO):
    def __init__(self, content, encoding=None):
        super().__init__(content)
        self.headers = {"Content-Encoding": encoding} if encoding else {}


class GzipXMLTVTests(unittest.TestCase):
    def setUp(self):
        self.xml = b'<tv><channel id="MBC"><display-name>MBC</display-name></channel></tv>'
        self.compressed = gzip.compress(self.xml)

    def test_magic_signature_decompresses_gzip(self):
        self.assertEqual(decode_xmltv_content(self.compressed), self.xml)

    def test_gzip_extension_fetches_xmltv(self):
        with patch("service.io.urllib.request.urlopen", return_value=FakeResponse(self.compressed)):
            self.assertEqual(fetch_xml("https://provider.test/guide.xml.gz"), self.xml)

    def test_gzip_http_header_without_extension(self):
        with patch("service.io.urllib.request.urlopen",
                   return_value=FakeResponse(self.compressed, "gzip")):
            self.assertEqual(fetch_xml("https://provider.test/guide.xml"), self.xml)

    def test_plain_xml_not_changed(self):
        with patch("service.io.urllib.request.urlopen", return_value=FakeResponse(self.xml)):
            self.assertEqual(fetch_xml("https://provider.test/guide.xml"), self.xml)

    def test_corrupt_gzip_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_xmltv_content(self.compressed[:-7], compressed=True)

    def test_compression_bomb_with_low_limit_rejected(self):
        compressed = gzip.compress(b"A" * 50000)
        with self.assertRaisesRegex(ValueError, "용량"):
            decode_xmltv_content(compressed, max_unpacked=256)

    def test_plain_xml_limit_is_enforced(self):
        with self.assertRaisesRegex(ValueError, "제한"):
            decode_xmltv_content(self.xml, max_unpacked=8)

    def test_download_bytes_limit_is_enforced(self):
        with patch("service.io.urllib.request.urlopen",
                   return_value=FakeResponse(self.compressed)):
            with self.assertRaisesRegex(ValueError, "다운로드 용량"):
                fetch_xml("https://provider.test/guide.xml.gz", max_bytes=4)

    def test_invalid_limit_rejected(self):
        with self.assertRaises(ValueError):
            decode_xmltv_content(self.compressed, max_unpacked=0)

    def test_no_credential_bearing_url_scheme(self):
        with self.assertRaises(ValueError):
            fetch_xml("file:///etc/passwd")


if __name__ == "__main__":
    unittest.main()
