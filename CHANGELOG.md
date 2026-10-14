# EPGCustom 변경 이력

## [0.1.2] - 2026-10-14

### 플러그인 메뉴 경로 보완
- GitHub 저장소 이름 `ff_epg`와 FlaskFarm 내부 패키지명 `epgcustom`이 다를 때 메뉴 링크가 잘못 만들어질 가능성 수정
- 플러그인 메뉴 진입 URI를 `__package__` 대신 `epgcustom`으로 명시해 FF BluePrint 경로와 통일
- FF 플러그인 설치가 `ff_epg` 폴더를 만드는 점을 문서에 반영
- v0.1.1의 설정 DB 바인드 자동 보완 코드는 그대로 유지

### 검증
- 패키지명과 메뉴 URI가 같은지 검사하는 단위 테스트 추가
- FF 4.x 소스의 `plugin_install`·`PluginManager`·`MenuManager`·`default_route` 구현을 비교
- Synology FF에 아직 배포하지 않은 개발본이며, 운영 적용 후 재검증 필요

## [0.1.1] - 2026-10-14

### 오류 수정
- Synology FF 4.x에 설치 직후 `plugin_load error`가 나타나던 현상 대응
- `SQLALCHEMY_BINDS`에 URI만 등록되고 `F.db.engines`에 `epgcustom`이 없을 때 엔진을 추가하는 호환 처리
- 기존 `epgcustom` 엔진이 존재하면 재생성하지 않고 설정 테이블만 확인
- 테이블 생성 중 예외 발생 시 새로 등록한 엔진을 해제하고 원래 예외를 유지
- 원본 EPG/MyEPG 및 FF·ALive·Shyni의 DB에는 접근·변경하지 않음

### 검증
- Python 3.10 단위 테스트 13개 통과(기존 8개 + DB 호환 테스트 5개)
- FlaskFarm 4.0 이미지의 Flask-SQLAlchemy 환경을 사용한 **격리된** SQLite 통합 테스트 통과: 누락 엔진 등록, 재사용, 테이블 생성, 설정 저장·조회
- Synology에 설치된 EPGCustom 0.1.0의 오류 로그를 근거로 수정하였으며, **Synology 0.1.1 운영 로딩은 아직 미검증**

### 적용·원복
- Synology FF의 epgcustom 플러그인만 Git 업데이트 후 FF 프로세스를 재시작하여 확인
- 문제가 지속되면 기존 플러그인 비활성화 또는 이전 Git 커밋으로 원복, Shyni EPG URL은 기존 설정 유지

## [0.1.0] - 2026-10-14

### 초기 구성
- FF 플러그인 인식용 info.yaml, setup.py 및 패키지 구조 추가
- 설정 화면, 수동 생성, 자동 스케줄러, XMLTV·상태 API 구성
- 기존 epg/myepg 원본 수정 없이 동작하도록 독립 패키지 설계

### 기능 추가
- M3U tvg-id 기준 채널 목록 추출 및 XMLTV 채널 매핑
- 여러 XMLTV 공급원 선택 및 오래된 편성 정보 제외
- EBS1/EBS 1처럼 이름에 공백이 다른 경우 매칭
- MBC와 MBC 뉴스 등 다른 채널의 오매핑 방지
- 중복 편성 항목 제거, 불량 시간 범위 제외
- 통합 XMLTV 파일 생성 및 채널별 미연결 보고서 출력
- 새 다운로드나 생성 실패 시 기존 XMLTV를 보존

### 보안과 안정성
- 공개 Git에 XMLTV, 인증 키, DB, 로그 및 환경 파일 제외
- 출력은 FF 영속 데이터 폴더 사용
- 입력 공급원의 실제 인증 URL을 출력 로그에 기록하지 않음

### 검증
- Oracle2 Python 3.10.12에서 단위 테스트 8개 통과
- Python 컴파일 구문 검사 통과
- **Synology FF 플러그인 실제 설치/동작은 아직 검증 전**
- **Oracle Shyni 운영 EPG 주소는 변경하지 않음**

### 이후 작업
- 실제 Synology FF 플러그인 로드 및 설정 화면 검증
- 정상 EPG 소스 확보 후 MBC, EBS2, 종합편성 등 채널 확대
- 실제 FF API 인증·스케줄러 연동 검사
