"""FlaskFarm 플러그인 진입점: 기존 epg/myepg 소스와 독립 운영."""
from plugin import F, create_plugin_instance

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

# FF 실행 중 추가 설치된 플러그인은 SQLAlchemy 3.x 엔진 등록이 누락될 수 있다.
# 다른 플러그인의 DB는 수정하지 않고 EPGCustom 설정 DB만 확인한다.
from .service.ff_compat import ensure_setting_bind  # noqa: E402
ensure_setting_bind(F, P)

from .mod_main import ModuleMain  # noqa: E402
P.set_module_list([ModuleMain])
