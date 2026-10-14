"""FF가 실행 중일 때 플러그인을 추가하는 경우의 DB 바인드 회귀 테스트."""
import logging
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from service.ff_compat import ensure_setting_bind


class FFCompatTests(unittest.TestCase):
    def setUp(self):
        self.db = SimpleNamespace(engines={}, create_all=Mock())
        self.F = SimpleNamespace(
            app=SimpleNamespace(
                config={"SQLALCHEMY_BINDS": {"epgcustom": "sqlite:////tmp/epgcustom-test.db"}},
                app_context=lambda: nullcontext(),
            ),
            db=self.db,
        )
        self.plugin = SimpleNamespace(package_name="epgcustom", logger=logging.getLogger("test"))

    def test_missing_bind_creates_engine_and_table(self):
        engine = Mock()
        factory = Mock(return_value=engine)
        self.assertTrue(ensure_setting_bind(self.F, self.plugin, factory))
        factory.assert_called_once_with("sqlite:////tmp/epgcustom-test.db")
        self.assertIs(self.db.engines["epgcustom"], engine)
        self.db.create_all.assert_called_once_with(bind_key="epgcustom")

    def test_existing_engine_is_reused(self):
        old = object()
        self.db.engines["epgcustom"] = old
        factory = Mock()
        self.assertFalse(ensure_setting_bind(self.F, self.plugin, factory))
        factory.assert_not_called()
        self.assertIs(self.db.engines["epgcustom"], old)
        self.db.create_all.assert_called_once_with(bind_key="epgcustom")

    def test_missing_config_fails_without_creating_engine(self):
        self.F.app.config["SQLALCHEMY_BINDS"] = {}
        with self.assertRaisesRegex(RuntimeError, "epgcustom"):
            ensure_setting_bind(self.F, self.plugin, Mock())
        self.db.create_all.assert_not_called()

    def test_table_creation_failure_rolls_back_engine(self):
        engine = Mock()
        self.db.create_all.side_effect = OSError("테스트 DB 쓰기 불가")
        with self.assertRaises(OSError):
            ensure_setting_bind(self.F, self.plugin, Mock(return_value=engine))
        self.assertNotIn("epgcustom", self.db.engines)
        engine.dispose.assert_called_once()

    def test_other_engines_are_not_modified(self):
        untouched = object()
        self.db.engines["epg"] = untouched
        ensure_setting_bind(self.F, self.plugin, Mock(return_value=Mock()))
        self.assertIs(self.db.engines["epg"], untouched)
        self.assertEqual(len(self.db.engines), 2)


if __name__ == "__main__":
    unittest.main()
