# EPGCustom — FF용 통합 편성표 플러그인

**저장소:** https://github.com/iamnosik/ff_epg
**패키지명:** epgcustom
**버전:** 0.3.0 (MyEPG 편성 보호 + KR1 자동 보완 + 정확한 채널명 매칭 + gzip·장애 대응, Synology 운영 적용 전)

**현재 권장 기본 구성:** FF ALive + `ff_iproxy2`의 Shyni hybrid 채널 목록 / MyEPG XMLTV 1순위 공급원. 이전 버전의 FF EPG 404 주소는 자동 기본값에서 제외했습니다. 다른 직접 설정한 공급원은 보존합니다.
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

**v0.1.2 단위 테스트 결과:** 총 14개 성공 (Oracle2, Python 3.10.12). Flask-SQLAlchemy 3.x 기반 격리 컨테이너에서도 뒤늦은 DB 바인드 등록과 SQLite 설정값 저장·조회에 성공했습니다. 이는 Synology FF에서 정상 로딩을 확인했다는 의미는 아닙니다.

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

## 0.1.2 — Git 폴더 이름과 FF 패키지 이름 분리

FF에서 `https://github.com/iamnosik/ff_epg`를 플러그인 설치하면 Git 폴더는 일반적으로 `ff_epg`가 되지만, `info.yaml`의 내부 FF 패키지명은 `epgcustom`입니다. FF는 플러그인 폴더 이름으로 로딩하고 설정 DB 엔진을 사전 등록하는 반면, 웹 API는 `package_name`을 사용하기 때문에 두 이름이 다른 점이 v0.1.0 로딩 오류의 핵심 원인으로 확인됐습니다.

v0.1.1에서 `epgcustom` DB 엔진 누락을 안전하게 보완했고, v0.1.2에서는 메뉴 진입 URI도 `epgcustom`으로 고정했습니다. Git 폴더 이름을 강제로 바꾸거나 기존 EPG/MyEPG를 수정할 필요가 없습니다.

**FF 내 실제 설치 경로는 `/data/plugins/ff_epg`일 수 있습니다.** 버전 확인 시에는 저장소 이름을 기준으로 폴더를 확인하고, 웹 주소에서는 `/epgcustom/...`을 사용합니다.

## v0.1.3 — 기본 EPG 공급원 자동 설정 (이전 버전 기록)

처음 FF의 **미분류 → EPGCustom → 통합 EPG 설정** 화면을 열면 비어 있는 필드는 다음과 같이 자동으로 채워 보입니다.

| 입력 필드 | 기본값 | 의미 |
|---|---|---|
| 채널 목록(M3U) | `ff://alive/api/m3u` | FF ALive에서 선택·활성화한 채널 목록 |
| 편성표 XMLTV (1순위) | `ff://myepg/api/epgall` | 기존 MyEPG 편성표 |
| 편성표 XMLTV (2순위) | `ff://epg/api/xml/alive` | 기존 FF EPG 보완 공급원 |
| 채널명 별칭 | `{"EBS 1": ["EBS1"]}` | 동일 채널명 차이 보정 |
| 스케줄러 | 기존 저장값 유지 | 자동 갱신을 임의로 켜지 않음 |

`ff://`는 일반 인터넷 주소가 아니라 **FF 내부 공급원 별칭**입니다. 실제 수집이 실행될 때만 FF의 `ToolUtil.make_apikey_url`을 통해 서버 주소·API 키를 적용합니다. 따라서 API 키를 사용자가 직접 찾아 적거나 GitHub에 등록할 필요가 없습니다.

- 기존 DB에 사용자가 저장한 M3U/XMLTV 주소가 있으면 이를 **절대 덮어쓰지 않습니다**.
- 이전 버전의 빈 값은 화면과 실제 실행에서만 기본값으로 보완하며 저장된 기존 값은 변경하지 않습니다.
- XMLTV 공급원은 위에서 아래 순으로 우선하며, 오류가 난 공급원은 건너뛰고 정상 공급원으로 생성합니다.
- 생성 전 M3U 채널 수와 각 XMLTV 공급원의 채널·편성 수를 검증하고, 생성 결과의 `연결진단`에 기록합니다.
- 생성 결과가 유효하지 않으면 기존에 정상 생성했던 XMLTV를 보존합니다.

**Shyni 채널 ID 주의:** 기본 M3U는 FF ALive 목록입니다. 현재 Oracle Shyni가 독립 Live Proxy의 `hybrid` M3U를 사용한다면, 추가 채널이나 `tvg-id`가 다를 수 있습니다. EPGCustom이 실제 Shyni 채널과 정확히 일치하도록 만들려면 **Synology FF에서 접근할 수 있는 Shyni의 M3U 주소**를 채널 목록에 별도로 지정하거나 두 목록의 ID를 비교해 보완해야 합니다. 기본값만으로 Shyni 232개(또는 이후 늘어난 채널) 모두가 자동 매칭된다고 보장하지 않습니다.

### 사용 순서

1. FF를 재시작해 최신 플러그인을 불러온 뒤 EPGCustom 버전이 `0.1.3`인지 확인합니다.
2. 통합 EPG 설정에서 기본 주소 3개가 표시되는지 확인합니다. 다른 주소가 이미 저장되어 있다면 기존 값이 우선합니다.
3. 처음에는 자동 갱신을 끈 상태에서 **설정 저장 → EPG 생성**을 선택합니다.
4. 생성이 끝난 뒤 상태 표시와 **EPG 연결률 보고서**를 확인합니다.
5. XMLTV 공급원이 누락되면 연결 보고서에서 `수집실패`과 원인을 확인합니다. 실제 FF 인증 URL을 로그에 그대로 남기지 않습니다.
6. 결과가 검증되기 전에는 기존 Shyni의 EPG 주소를 변경하지 않습니다.

**검증 상태:** Oracle2에서 27개 단위·통합 흐름 테스트 성공. Synology FF의 실제 EPG 생성 및 Shyni 전환은 후속 검증 단계입니다.


## v0.2.0 — 실제 FF/MyEPG 운영에 맞춘 전면 재검증

### 설정 화면
- MyEPG처럼 최종 `EPGALL` 주소와 생성·오류 상태, 마지막 생성 시각, 연결률 보고서를 맨 위에 표시합니다.
- M3U/XMLTV 공급원과 이름 별칭 설정은 고급 설정을 펼쳐서 수정합니다.
- 기본 EPG 공급원은 MyEPG입니다(v0.2.1부터). 기존 사용자 설정과 스케줄러 상태는 바꾸지 않습니다.

### 편성표 정확도
- XMLTV `YYYYMMDDHHMMSS ±HHMM` 시간의 초와 시간대를 온전히 분석합니다. 기존 버전에서 14자리 시간을 12자리로 잘라 읽을 수 있던 문제를 수정합니다.
- 오래된 프로그램·유효하지 않은 시간 범위·중복 편성 항목을 제외합니다.
- 동일 채널에 여러 공급원이 있다면 편성 시간 범위를 비교하고, 우선 공급원의 유효 커버리지가 최고 공급원 대비 80% 미만일 때만 더 충분한 공급원을 선택합니다.
- 서로 다른 공급원의 편성표를 한 채널에 무조건 합치지 않아 중복·시간 충돌을 방지합니다.
- MBC와 MBC 뉴스 등 서로 다른 방송은 유사한 이름만으로 매핑하지 않습니다.
- 최종 XMLTV가 기존보다 실제로 더 많은 채널을 제공하는지는 원본 데이터 품질에 좌우됩니다. 편성표가 없는 채널을 임의로 만들어내지 않습니다.

### 안전한 운영 및 문제 해결
- 작업 실패 시 이전 `epgall.xml` 파일을 보존합니다.
- 상태 API에는 현재 상태, 마지막 안전한 오류 설명, 마지막 성공 시각, 마지막 생성 보고서를 함께 제공합니다.
- API 인증 키가 포함된 실제 외부 주소는 Git이나 오류 화면에 기록하지 않습니다.
- FF 플러그인 로딩, 실제 Synology 내부에서 생성 요청, Shyni 채널 ID 연동은 운영 환경에서 별도 확인해야 합니다.

### 테스트
- Oracle2 Python 단위 테스트에서 XMLTV 초·시간대·오염된 입력·공급원 커버리지·MBC 구별을 추가 검사합니다.
- GitHub 업로드 후 Synology FF가 자동 갱신되는 환경이라면 운영 시간대에 FF를 재시작해 `0.2.0`과 `loading: true`를 확인하세요.
- **이 검증 전에는 Shyni의 기존 EPG URL을 변경하지 마세요.**


## v0.2.1 — Shyni hybrid 채널 232개 정확히 매칭

2026-10-14 현재 Synology FF와 Oracle Shyni를 읽기 전용으로 대조해 다음을 확인했습니다.

| 항목 | 확인된 결과 |
|---|---:|
| FF ALive M3U 실제 항목 / 고유 채널 ID | 229 / 218 |
| FF ff_iproxy2 M3U 실제 항목 | 35 |
| Shyni hybrid M3U 항목 / 고유 채널 ID | 243 / 232 |
| ALive에서 제외하는 KBS 1TV·KBS 2TV 중복 표시 항목 | 2 |
| iproxy2에서 추가되는 채널 | 16 |
| **EPGCustom 새 채널 ID와 Shyni hybrid 채널 ID 차이** | **0개** |

### 변경된 기본 공급원

- 채널 목록: `ff://alive/api/m3u` + `ff://ff_iproxy2/api/m3u` (Shyni hybrid 호환 기본 ON)
- XMLTV: `ff://myepg/api/epgall` 한 곳만 기본 사용
- Synology FF의 `/epg/api/xml/alive`는 **HTTP 404로 확인되어 기본 공급원에서 제외**
- v0.2.0에서 자동 저장된 정확히 동일한 MyEPG+FF EPG 두 줄은 새로운 MyEPG 단일 기본값으로 해석합니다. 다른 직접 지정 URL은 변경하지 않습니다.
- ff_iproxy2의 M3U 조회가 실패하면 ALive 채널만 사용하고 `ALive 폴백` 경고를 보고서·최근 생성 상태에 남깁니다.
- 기본 ALive 목록이 아닌 사용자 M3U URL을 지정했다면 자동 합치기를 적용하지 않습니다.
- 원본 ALive·ff_iproxy2 M3U 안의 재생 주소는 **출력 XMLTV에는 기록되지 않으며**, 편성 채널 식별에만 사용합니다.

### EPG 공급원 한계와 추가 개발

실제 MyEPG XMLTV를 사용한 독립 시험에서는 Shyni와 동일한 **232개 ID 중 49개 채널 연결, 183개 미연결, 총 1,959개 편성 항목**이었습니다. MBC 본채널·EBS2·JTBC·YTN은 데이터가 부족했고 EBS1·KBS1·KBS2는 연결됐습니다.

이는 코드에서 제공자별 편성표를 만들어 채운 결과가 아니라 MyEPG가 제공한 현재 XMLTV와 명시적인 채널 ID 매칭 결과입니다. **MBC 등 편성표 누락은 MyEPG 추가 공급원 활성화 또는 별도의 최신 XMLTV 확보가 필요**합니다. 다른 방송의 EPG를 비슷한 이름으로 잘못 대입하지 않습니다.

### FF 업데이트 후 확인할 사항

1. 플러그인 목록에서 `version: 0.2.1`, `loading: true` 확인
2. EPGCustom 화면에 **Shyni hybrid 채널 구성 호환** ON 확인
3. 기존 FF/MyEPG/Shyni의 EPG URL은 그대로 두고 수동 EPG 생성
4. 생성 보고서에서 `채널목록진단.모드: Shyni hybrid 호환`, `최종채널ID: 232`, `IProxy추가채널: 16` 확인
5. 보고서에 `ALive 폴백`이면 해당 원인을 먼저 해결하고 Shyni 설정을 교체하지 않음
6. XMLTV 232개 채널 `id`와 EPG 연결 개수를 확인한 후에만 Shyni EPG URL 변경을 검토

**테스트 결과:** Python 자동 시험 43개 통과, 실제 Synology/Oracle의 M3U로 232개 채널 ID 집합의 완전 일치를 별도 검증했습니다. 단, Synology FF에 새 버전 설치·재시작은 아직 실행하지 않았습니다.


## v0.3.0 — 기존 MyEPG 보호 및 KR1 추가 편성표

### 운영 기본값

| 항목 | 값 | 설명 |
|---|---|---|
| M3U 기준 | \`ff://alive/api/m3u\` + ff_iproxy2 | Shyni hybrid 활성 목록을 FF에서 합성 |
| XMLTV 기본 | \`ff://myepg/api/epgall\` | 기존 사용자 설정을 그대로 유지 |
| KR1 보조 | ON | MyEPG 기본 목록인 경우 \`https://epgshare01.online/epgshare01/epg_ripper_KR1.xml.gz\` 실행 시 자동 보완 |
| MyEPG 우선 | ON | MyEPG에 유효 편성이 있으면 KR1 편성으로 바꾸지 않음 |
| 자동 스케줄러 | 기존 값 그대로 | 기존 상태/주기를 임의 변경하지 않음 |
| 검증된 별칭 | EBS 1→EBS1, TV CHOSUN→TV조선, ANIMAX→애니맥스 | 사용자 지정 JSON이 있는 항목은 사용자 설정 우선 |

기본 화면은 MyEPG와 비슷하게 **통합 EPGALL 주소, 생성 상태, 연결률**을 먼저 표시합니다. KR1 연동 및 MyEPG 우선 ON/OFF는 자동 생성 설정 카드에서 바꿀 수 있고, 직접 편집하는 원본 URL·별칭 JSON은 고급 설정에 유지합니다.

**사용자 설정 보존:** 예전 설치의 \`main_epg_urls\`가 \`ff://myepg/api/epgall\` 한 줄이라면 해당 값은 변경하지 않고, KR1 연동 ON일 때만 런타임 공급원을 하나 더 붙입니다. MyEPG와 별개로 직접 등록한 공급원이 있다면 자동으로 KR1을 추가하지 않습니다. 사용자 별칭에서 \`"ANIMAX": []\`처럼 빈 배열을 지정하면 해당 기본 별칭을 사용하지 않습니다.

### 정확도와 장애 대응

- 원본 ID·정확한 표시명·검증된 별칭을 우선하므로 \`SPOTV Prime\`과 \`SPOTV Prime+\`를 구분합니다. 정규화 단계에서도 \`+\`, \`&\`를 보존합니다.
- 외부 피드는 **압축 다운로드/해제 각각 64MiB 상한**을 지키며 손상된 gzip은 저장하지 않습니다. 공급원 내용은 중복 파싱하지 않습니다.
- KR1 또는 MyEPG가 실패하고 이전에 성공한 \`epgall.xml\`이 존재하면 **기존 XMLTV와 보고서를 그대로 유지**하며 현재 상태를 실패로 표시합니다. 최초 생성이고 일부 공급원만 성공했다면 \`부분 성공\`으로 표시합니다.
- 작업 보고서에 \`공급원별연결\`, \`공급원정책\`, \`연결진단\`, \`수집실패\`가 나오며 비밀 API 키는 포함하지 않습니다.
- 공개 EPG 공급원에 없는 실제 방송 편성을 임의 생성하거나 서로 다른 채널의 방송을 복사하지 않습니다.

### 2026-10-14 실제 데이터 독립 시험

Shyni 활성 채널 233개와 당시 MyEPG·KR1 실데이터를 사용해 운영 파일을 쓰지 않고 시험했습니다.

- **MyEPG 단독:** 52개 채널, 2,051개 편성 항목
- **MyEPG+KR1:** **101개 연결**, 5,832개 편성 항목 (**MyEPG 52개 유지 / KR1 49개 추가**)
- MBC·JTBC·MBN·TV CHOSUN·채널A·YTN·연합뉴스TV는 KR1, EBS1·SPOTV Prime·Prime+·Prime2는 MyEPG로 연결
- **EBS2는 미연결**. KR1에 제공되는 'EBS 플러스2'는 EBS2와 다릅니다.
- 수치는 실제 배포 후 변할 수 있으며 v0.3.0 Synology 실제 구동 검증을 통과하기 전 Shyni EPG URL을 교체하지 않습니다.

### 데이터 이용 주의

KR1은 EPGShare01이 제공하는 외부 XMLTV입니다. 네트워크 호출 및 자동 갱신은 KR1 옵션이 켜져 있을 때 수행됩니다. 서비스 사용 조건, 대량 요청·공개 재배포 허용 범위는 사용자가 검토해야 하며, **코드의 존재 자체가 데이터 재배포 허락을 의미하지 않습니다.** 공개 서비스로 재배포하기 전에 공급원 조건을 확인하고, 필요하다면 KR1을 끄고 MyEPG만 사용하세요.
