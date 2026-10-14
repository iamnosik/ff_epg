# EPGCustom — FF용 통합 편성표 플러그인

**저장소:** https://github.com/iamnosik/ff_epg
**패키지명:** epgcustom
**버전:** 0.1.1 (FF 동적 설치 시 DB 바인드 오류 수정본, Synology 적용 전 검증 필요)
**언어:** Python 3.10 및 FlaskFarm(FF) 플러그인

## 개발 목적

Oracle Shyni의 라이브 TV 채널은 232개이나 기존 FF/MyEPG XMLTV와 실제 매칭되는 채널은 약 47개입니다(2026-10-14 조사 기준). 일부는 수집원이 부족하고, 일부는 채널 이름/ID가 달라 연결되지 않습니다.

EPGCustom은 **기존 제작자 Git 저장소를 수정하지 않고**, 이미 제공되는 M3U 및 XMLTV API를 읽어서 채널별로 편성표를 매칭·정리해 **독립 XMLTV API**로 제공합니다.

- flaskfarm/epg: https://github.com/flaskfarm/epg (참고 및 EPG 공급원)
- myepg/myepg: https://github.com/myepg/myepg (참고 및 EPG 공급원)
- FF/ALive/Shyni/Live Proxy: 기존 운영 환경 변경 없이 유지

## 주요 기능(v0.1.x)

1. 원본 M3U에서 tvg-id → tvg-name → 표시명 순으로 채널 ID 결정
2. 여러 XMLTV 공급원의 편성표 수집 및 우선순위 적용
3. 채널 이름의 대소문자, 공백, 구두점 차이 정규화
4. 명시적 별칭 지원: 예) EBS 1 ↔ EBS1
5. 중복 프로그램 제거 및 시간 범위 검증
6. 오래된 데이터가 있는 공급원을 건너뛰고 다음 공급원 채택
7. 공급원별 채널 연결 현황, 미연결 채널 목록, 오류 유형 보고
8. XMLTV 파일을 원자적으로 저장하며, 새 수집 실패 시 직전 파일 보존

**주의:** 편성표가 없는 방송의 제목이나 시간을 추정해서 생성하지 않습니다. 지상파 MBC와 'MBC 뉴스', 'MBC every1' 등은 서로 다른 채널입니다. MBC/EBS2의 실제 편성표는 별도의 정상 수집원이 확보되어야 합니다.

## 플러그인 구조

~~~text
epgcustom/
├── __init__.py                패키지 진입
├── info.yaml                  FF 플러그인 메타데이터
├── setup.py                   FF 플러그인 등록
├── mod_main.py                설정 화면·스케줄러·API
├── service/
│   ├── core.py                M3U·XMLTV 파서 및 매핑 엔진
│   └── io.py                  HTTP 수집·안전한 파일 저장
├── templates/
│   └── epgcustom_main_setting.html
├── tests/
│   └── test_core.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── INSTALLATION.md
│   └── GIT_COMMITS.md
└── CHANGELOG.md
~~~

XMLTV 및 보고서 파일은 FF 데이터 폴더의 epgcustom/ 하위에 저장합니다. Git 소스 폴더에 인증정보·로그·DB·XML 산출물을 올리지 않습니다.

## 설정

FF 설정 페이지에서 다음 값을 입력합니다.

| 설정 항목 | 의미 |
|---|---|
| M3U 주소 | Shyni 채널 목록과 동일한 tvg-id가 포함된 전체 M3U |
| 편성표 XMLTV 주소 | 한 줄에 하나씩; 위에 쓴 소스가 우선 |
| 채널명 별칭(JSON) | 예: {"EBS 1": ["EBS1"]} |
| 자동 갱신 | 기본적으로 비활성. 검증 완료 후 활성화 권장 |
| 갱신 주기 | 기본값: 0 */6 * * * (6시간 주기) |

XMLTV 공급원은 예컨대 기존 FF의 /myepg/api/epgall 와 /epg/api/xml/alive 등을 이용할 수 있습니다. 실제 URL에는 인증 키가 필요할 수 있습니다. **API 키가 포함된 실제 URL을 GitHub 문서·Issues·로그에 올리지 마세요.**

## API (FF에 설치한 후)

- /epgcustom/api/epgall : 통합 편성표 XMLTV
- /epgcustom/api/status : 연결된 채널 수·미연결 채널·수집 실패 사유를 포함한 보고서

FF의 인증 설정에 따라 apikey가 필요할 수 있습니다. 실제 API 라우팅·인증·메뉴는 FF 설치 후 별도 통합 테스트가 필요합니다.

## 테스트 방법

FF 설치 없이 순수 엔진 검증:

~~~bash
cd /docker/projects/ff_epg
python3 -m unittest discover -s tests -v
python3 -m compileall -q setup.py mod_main.py service tests
~~~

**v0.1.1 단위 테스트 결과:** 총 13개 성공 (Oracle2, Python 3.10.12). Flask-SQLAlchemy 3.x 기반 격리 컨테이너에서도 뒤늦은 DB 바인드 등록과 SQLite 설정값 저장·조회에 성공했습니다. 이는 Synology FF에서 정상 로딩을 확인했다는 의미는 아닙니다.

## 운영 적용 및 원복

1. 테스트 환경에만 먼저 플러그인을 설치해 FF 시작 로그·설정 메뉴를 확인합니다.
2. 처음에는 테스트용 M3U와 XMLTV를 설정하고 EBS1 및 MBC 매핑을 검사합니다.
3. 기존 Shyni EPG 주소는 바꾸지 않은 채 새로운 XMLTV 결과를 검사합니다.
4. 검증이 완료되면 Shyni EPG URL만 EPGCustom으로 변경합니다.
5. 문제가 있으면 Shyni EPG URL을 기존 MyEPG 주소로 복원합니다.

구체적인 절차: docs/INSTALLATION.md

## Git 업데이트 원칙

- 원본 epg와 myepg의 Git 저장소는 직접 변경하지 않습니다.
- 새 기능은 ff_epg 저장소만 수정하고 기능별로 나누어 커밋합니다.
- 커밋 제목과 본문, 문서, 변경 이력은 **한글로 자세히 기록**합니다.
- SSH 개인키 및 인증 토큰을 Git에 절대 올리지 않습니다.

한글 커밋 규칙: docs/GIT_COMMITS.md

## 2026-10-14 실제 EPG 원본 읽기 전용 검증

- 현재 Oracle Shyni의 채널 M3U 232개와 Synology MyEPG XMLTV를 사용했습니다.
- 기존 Shyni EPG 연결은 약 47개였고, EPGCustom 매핑 결과 **49개 연결**, 미연결 183개, 생성 편성 항목 2,053개로 확인했습니다.
- EBS 1은 편성표 연결에 성공했고, MBC 본채널은 MyEPG 원본에 해당 데이터가 없어 여전히 미연결입니다.
- 이는 FF 설치 검증이 아닌 **순수 EPG 통합 엔진의 실제 데이터 읽기 테스트**입니다.
- 운영 Shyni DB, FF 플러그인, Live Proxy 및 설정은 수정하지 않았습니다.

## 0.1.1 — FF의 DB 바인드 로딩 오류 보완

Synology FF에 0.1.0을 설치한 뒤 `plugin_load error`와 `UnboundExecutionError: Bind key 'epgcustom'`가 보고되었습니다. FF 4.x는 시작 시 기존 플러그인의 SQLite 엔진을 만들지만, 동작 중 설치한 플러그인의 URI가 나중에 추가되면 실제 엔진 딕셔너리에 등록되지 않을 수 있습니다.

0.1.1은 `setup.py`에서 EPGCustom의 설정 DB 엔진 존재 여부를 확인하고, 누락 시에만 등록하며 설정 테이블을 준비합니다. 기존 FF 엔진이나 다른 EPG 플러그인의 데이터는 변경하지 않습니다. 오류가 다시 발생하면 GitHub에서 버전 및 FF 플러그인 JSON의 마지막 Traceback을 확인하세요.

**주의:** FF에 설치된 플러그인을 새 Git 버전으로 갱신하고 재로딩하기 전까지 이 변경은 적용되지 않습니다. Synology 운영 FF의 실제 테스트는 아직 진행하지 않았습니다.
