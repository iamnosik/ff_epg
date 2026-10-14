"""FF 저장소 폴더명(ff_epg)과 실제 API 패키지명(epgcustom)이 달라도 링크가 일치하는지 검사."""
import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PluginIdentityTests(unittest.TestCase):
    def test_ff_menu_uri_matches_blueprint_package_name(self):
        info_text = (ROOT / "info.yaml").read_text(encoding="utf-8")
        package = re.search(r'^package_name:\s*["\']([^"\']+)["\']', info_text, re.M)
        self.assertIsNotNone(package)
        tree = ast.parse((ROOT / "setup.py").read_text(encoding="utf-8"))
        setting_dict = next(
            node.value for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "setting" for t in node.targets)
        )
        def key_value(d, name):
            return next(v for k, v in zip(d.keys, d.values)
                        if isinstance(k, ast.Constant) and k.value == name)
        menu_node = key_value(setting_dict, "menu")
        menu_uri = ast.literal_eval(key_value(menu_node, "uri"))
        self.assertEqual(menu_uri, package.group(1))
        # FF는 Git 폴더명을 독립적으로 정할 수 있다. 메뉴는 디렉터리 이름에 의존하지 않는다.
        self.assertEqual(menu_uri, "epgcustom")
        menu_list = key_value(menu_node, "list")
        menu_urls = [ast.literal_eval(key_value(item, "uri")) for item in menu_list.elts]
        self.assertIn("main/setting", menu_urls)
        self.assertIn("main/diagnostics", menu_urls)


if __name__ == "__main__":
    unittest.main()
