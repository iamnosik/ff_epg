"""EPGCustom에서 사용하는 FF 내부 공급원 표기와 안전한 기본값.

ff:// 주소는 FF와 같은 서버의 ALive/MyEPG를 가리키는 *별칭*이다.
실제 API 키와 DDNS 주소는 FF가 실행할 때 ToolUtil로 변환한다.
Git 소스나 설정 DB에는 API 키를 저장하지 않는다.
"""
from __future__ import annotations
from urllib.parse import urlsplit

# ALive에서 활성화한 채널 목록을 기본으로 사용한다.
# 전체 소스 강제 출력(m3uall)은 중복/미선택 채널이 많을 수 있다.
DEFAULT_M3U = "ff://alive/api/m3u"
DEFAULT_EPGS = ("ff://myepg/api/epgall", "ff://epg/api/xml/alive")

FF_SOURCE_PATHS = {
    DEFAULT_M3U: "/alive/api/m3u",
    "ff://alive/api/m3uall": "/alive/api/m3uall",
    DEFAULT_EPGS[0]: "/myepg/api/epgall",
    DEFAULT_EPGS[1]: "/epg/api/xml/alive",
}


def m3u_setting(saved_value: str | None) -> str:
    """설정이 비어 있는 기존 설치에서도 기본값을 화면과 실행 양쪽에 제공."""
    return (saved_value or "").strip() or DEFAULT_M3U


def epg_settings(saved_value: str | None) -> list[str]:
    """빈 설정은 MyEPG 우선, FF EPG 보완 순서로 자동 설정한다."""
    lines = [
        text.strip() for text in (saved_value or "").splitlines()
        if text.strip() and not text.lstrip().startswith("#")
    ]
    return lines if lines else list(DEFAULT_EPGS)


def epg_setting_display(saved_value: str | None) -> str:
    return "\n".join(epg_settings(saved_value))


def source_url(value: str, make_ff_url) -> str:
    """ff:// 별칭에 대해서만 FF 런타임의 실제 주소·인증 값을 생성한다.

    make_ff_url은 FF ToolUtil.make_apikey_url 같은 함수를 넘긴다.
    사용자가 입력한 원본 http(s) URL은 그대로 유지한다.
    """
    value = (value or "").strip()
    if value in FF_SOURCE_PATHS:
        value = make_ff_url(FF_SOURCE_PATHS[value])
    elif value.startswith("ff://"):
        raise ValueError("지원하지 않는 FF 내부 주소입니다.")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("유효한 HTTP(S) 주소가 아닙니다. FF의 DDNS 설정을 확인하세요.")
    if parts.username or parts.password:
        raise ValueError("URL에 계정명이나 비밀번호를 포함하지 마세요.")
    return value
