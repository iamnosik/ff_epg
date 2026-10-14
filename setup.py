"""FlaskFarm 플러그인 진입점: 기존 epg/myepg 소스와 독립 운영."""
from plugin import create_plugin_instance

setting = {
    "filepath": __file__,
    "use_db": True,
    "use_default_setting": True,
    "home_module": None,
    "menu": {
        "uri": __package__,
        "name": "EPGCustom",
        "list": [
            {"uri": "main/setting", "name": "통합 EPG 설정"},
            {"uri": "manual", "name": "문서", "list": [
                {"uri": "README.md", "name": "한글 사용 설명서"},
                {"uri": "CHANGELOG.md", "name": "변경 이력"},
            ]},
            {"uri": "log", "name": "로그"},
        ],
    },
    "setting_menu": None,
    "default_route": "normal",
}

P = create_plugin_instance(setting)
from .mod_main import ModuleMain  # noqa: E402
P.set_module_list([ModuleMain])
