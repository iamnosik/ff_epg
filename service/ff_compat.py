"""FF 4.x에서 나중에 설치한 플러그인의 SQLite 바인드를 안전하게 초기화한다.

Flask-SQLAlchemy 3.x는 SQLAlchemy(app) 초기화 시점의 바인드만 엔진으로
등록한다. FF를 실행한 뒤 새 플러그인을 설치하면 create_plugin_instance()가
설정에 URI를 넣더라도 F.db.engines에는 추가되지 않을 수 있다.
"""
from __future__ import annotations


def ensure_setting_bind(F, plugin, engine_factory=None) -> bool:
    """누락된 플러그인 DB 엔진만 생성하고 설정 테이블을 준비한다.

    Args:
        F: FF 프레임워크 객체(app, db, config 포함).
        plugin: create_plugin_instance()로 만든 객체.
        engine_factory: 테스트에서 주입하는 엔진 생성 함수.
    Returns:
        누락된 엔진을 새로 등록했다면 True.
    """
    bind_key = plugin.package_name
    with F.app.app_context():
        uri = (F.app.config.get("SQLALCHEMY_BINDS") or {}).get(bind_key)
        if not uri:
            raise RuntimeError(
                f"EPGCustom 설정 DB 주소를 찾지 못했습니다: {bind_key}. "
                "플러그인의 use_db 설정과 FF의 path_data 설정을 확인하세요."
            )

        engines = F.db.engines
        if bind_key in engines:
            # FF 시작 시 이미 만든 엔진이면 재사용하고 DB 테이블만 확인한다.
            F.db.create_all(bind_key=bind_key)
            return False

        if engine_factory is None:
            from sqlalchemy import create_engine
            engine_factory = create_engine

        # EPGCustom에만 바인드를 보완한다. system, epg, myepg는 건드리지 않는다.
        new_engine = engine_factory(uri)
        engines[bind_key] = new_engine
        try:
            F.db.create_all(bind_key=bind_key)
        except Exception:
            # 초기 테이블 생성까지 실패하면 절반만 등록된 엔진을 남기지 않는다.
            engines.pop(bind_key, None)
            dispose = getattr(new_engine, "dispose", None)
            if callable(dispose):
                dispose()
            raise

        plugin.logger.info(
            "EPGCustom 설정 DB 엔진 등록 완료: %s (신규 플러그인 호환 처리)",
            bind_key,
        )
        return True
