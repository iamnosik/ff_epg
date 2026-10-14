# EPGCustom 설치 및 운영 검증 가이드

**현재 상태: Synology FF에서 v0.1.0 설치는 인식되었으나 설정 DB 바인드 초기화 오류로 로딩 실패. v0.1.2 수정본을 GitHub에 반영하는 중이며 Synology 운영 검증 전입니다.** 기존 FF·ALive·Shyni 설정은 유지합니다.

## 1. 사전 확인

- FF의 사용자 정의 플러그인 폴더 위치와 영속 볼륨 매핑 확인
- FF 컨테이너의 Python·FlaskFarm API 버전 확인
- 기존 epg 및 myepg Git 저장소와 설정 백업
- 기존 Shyni Live TV M3U와 EPG 주소 백업
- 테스트 기간 동안 기존 자동 수집 작업을 중지하거나 수정할 필요는 없습니다.

**주의:** Oracle2 작업 폴더 /docker/projects/ff_epg는 개발용입니다. Synology FF 플러그인 폴더가 아닙니다.

## 2. 테스트 환경에 배포

1. FF 컨테이너의 실제 플러그인 경로를 확인합니다.
2. 해당 경로에 새 패키지 디렉터리 epgcustom을 만듭니다.
3. iamnosik/ff_epg 저장소 코드를 epgcustom 디렉터리로 복제합니다.
4. FF의 사용자 플러그인 등록 방식에 따라 플러그인을 활성화합니다.
5. FF 시작 로그에서 EPGCustom 로딩 오류가 없는지 확인합니다.
6. 기존 EPG/MyEPG 메뉴와 API가 그대로 작동하는지 확인합니다.

FF의 실제 플러그인 등록·관리 방식과 재시작 필요 여부는 **Synology 환경 확인 후 결정**합니다. 검증 없이 운영 FF를 재시작하지 않습니다.

## 3. 설정 값

- M3U: 현재 Shyni Live TV가 사용하는 채널 목록과 동일한 채널 ID를 가진 주소
- EPG XMLTV: 기존 FF EPG 및 MyEPG API (한 줄당 하나)
- 별칭 JSON: {"EBS 1": ["EBS1"]}
- 자동 갱신: 최초에는 끔, 테스트 후 활성화

URL에 들어간 API 키를 GitHub에 커밋하지 마세요.

## 4. 검증

- 설정 화면 렌더링 및 'EPG 생성' 명령 동작
- EBS 1이 원본 EBS1 편성표와 매칭되는지 검사
- MBC 본채널이 MBC 뉴스와 잘못 매칭되지 않는지 검사
- 일부 공급원 실패에도 나머지 공급원을 이용하는지 검사
- XMLTV의 채널 id가 M3U tvg-id와 일치하는지 검사
- Shyni가 XMLTV를 읽을 때 채널과 편성표가 정상 연결되는지 검사
- API 인증, FF 재시작, 자동 갱신 및 로그 상태 검사

## 5. 운영 적용

위 검증 후에만 Shyni EPG URL을 EPGCustom의 /epgcustom/api/epgall 주소로 변경합니다. M3U 재생 주소와 기존 Live Proxy 설정은 건드리지 않습니다.

## 6. 원복

- Shyni 설정의 EPG 주소를 기존 /myepg/api/epgall 주소로 복원합니다.
- EPGCustom 자동 실행을 해제합니다.
- 필요하면 플러그인을 비활성화하되, 최초에는 파일과 설정을 보존합니다.
- 기존 epg/myepg/Shyni/ALive의 원본 파일이나 DB는 EPGCustom이 수정하지 않습니다.

## 7. v0.1.0 로딩 실패 시 대처 (2026-10-14)

### 확인된 로그

- 화면: EPGCustom `loading: false`, `status: plugin_load error`
- Traceback: `sqlalchemy.exc.UnboundExecutionError: Bind key 'epgcustom' is not in 'SQLALCHEMY_BINDS' config.`
- FF 4.x SQLAlchemy 엔진은 시작 시 플러그인 디렉터리를 스캔하며, 플러그인 설치 후 재로딩에서는 엔진 누락이 발생할 수 있습니다.

### v0.1.1 보완 사항

- EPGCustom 설정 DB 바인드가 이미 있으면 엔진을 변경하지 않습니다.
- 없으면 `SQLALCHEMY_BINDS`에 등록된 `epgcustom` 주소로 엔진을 등록합니다.
- 설정 테이블을 확인하고 생성합니다. 실패할 경우 부분적으로 등록된 엔진을 해제하고 예외를 상위로 전달합니다.
- 기본 자동 갱신은 OFF이므로 최초 로딩만으로 외부 EPG 소스에 접근하지 않습니다.

### Synology 반영 순서 (작업 전 승인 필요)

1. Synology의 FF가 사용하는 `epgcustom` 실제 설치 폴더를 확인합니다.
2. Git 추적 폴더라면 해당 폴더가 깨끗한지 확인한 뒤 `git pull --ff-only`로 최신 `main`을 받습니다. 강제 덮어쓰기와 `git reset --hard`를 사용하지 않습니다.
3. 실제 `info.yaml`이 0.1.1로 변경됐는지 확인합니다.
4. FF 컨테이너를 **계획된 시간에** 재시작하거나 관리 기능으로 플러그인 재로딩 후 상태를 확인합니다.
5. FF 플러그인 JSON에서 `loading: true`와 정상 상태를 확인하고, 오류가 있으면 Traceback을 확인합니다.
6. 기존 MyEPG/ALive API가 정상인지 확인한 뒤 EPGCustom 설정 페이지와 새 XMLTV 생성 명령을 시험합니다.

**운영 주의:** 현재 사용자에게서 받은 로그만으로는 Synology에 v0.1.1을 실제 반영했다는 뜻이 아닙니다. FF 컨테이너 재시작과 Shyni EPG URL 변경은 별도 승인 후 진행합니다.

## 8. FF에서 저장소 폴더명과 API 패키지명 구분하기

- `ff_epg`는 GitHub 저장소 이름이자 FF 설치기가 기본으로 만드는 디렉터리 이름입니다.
- `epgcustom`은 `info.yaml`에 선언한 플러그인 패키지명입니다.
- Git 업데이트 확인 경로는 일반적으로 `/data/plugins/ff_epg`입니다. 실제 위치는 Synology FF 컨테이너에서 확인해야 합니다.
- 웹 메뉴 및 XMLTV 주소는 `/epgcustom/main/setting`, `/epgcustom/api/epgall`입니다.
- FF는 시작 시 플러그인 **디렉터리명**으로 초기 SQLAlchemy 엔진 목록을 만들므로, DB 바인드 `epgcustom`은 호환 함수가 확인·등록합니다.
- v0.1.2는 메뉴도 FF 패키지명과 일치하도록 수정했습니다.

### 갱신 전 확인 (Synology 컨테이너 내부)

~~~bash
# 실제 설치 폴더가 ff_epg인지 먼저 확인
ls -ld /data/plugins/ff_epg /data/plugins/epgcustom 2>/dev/null
# 설치된 플러그인이 Git 저장소라면 현재 수정 사항을 확인
git -C /data/plugins/ff_epg status --short
# 오류 없이 Git만 최신 상태로 갱신 (기존 수정 파일 강제 덮어쓰기 금지)
git -C /data/plugins/ff_epg pull --ff-only
# 버전 0.1.2 확인
grep '^version:' /data/plugins/ff_epg/info.yaml
~~~

위 예시는 FF 설치기의 기본 디렉터리명 `ff_epg`를 가정합니다. 실제 경로가 다르면 경로를 변경해야 합니다. 파일 갱신 후 **계획된 시점에 FF 재시작** 및 플러그인 JSON 로딩 상태 확인이 필요합니다. 현재 Shyni EPG URL은 유지하세요.
