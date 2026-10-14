# EPGCustom 구조 및 채널 매칭 설계

## 원칙

EPGCustom은 **재생 프록시가 아닙니다.** 영상 스트림은 기존 ShyniLiveProxy와 ALive가 그대로 담당하고, EPGCustom은 EPG XMLTV 수집·검증·병합만 담당합니다.

~~~text
ALive M3U ───────────────────────┐
                                │
FF EPG XMLTV ─────┐             │
                  ├─ EPGCustom ─┴─ Shyni 호환 XMLTV
MyEPG XMLTV ──────┘   │
                      └─ 연결 결과 JSON
~~~

## 채널 연결 방법

1. M3U tvg-id와 XMLTV channel id의 정확 일치부터 검사합니다.
2. XMLTV display-name과 M3U 표시명의 정규화 일치를 검사합니다.
3. 지정된 별칭 테이블과 XMLTV ID·이름을 검사합니다.
4. 후보 XMLTV가 여러 개라면 자동 선택하지 않습니다.
5. 제목/시간이 유효한 편성표가 있는 가장 높은 우선순위 공급원을 사용합니다.

문자 정규화는 유니코드 NFKC + 영숫자만 남기는 방식입니다. 임의의 방송사를 추론하거나 유사 문자열 퍼지 매칭을 수행하지 않습니다.

## 시간·중복

- XMLTV 시간대 정보가 있으면 해당 오프셋을 사용합니다.
- 시간대가 없으면 한국 표준시(+09:00)를 기본값으로 가정합니다.
- 종료 시간이 시작 시간보다 늦어야 하며 현재 기준 2시간 이전의 오래된 자료는 제외합니다.
- 동일 시작·종료·제목의 중복 프로그램을 제거합니다.
- 단일 채널에 여러 공급원의 프로그램을 임의로 이어 붙이지 않습니다.

## 기록 및 보안

- 성공: 생성된 epgall.xml과 report.json을 FF 영속 데이터 영역에 원자적으로 저장합니다.
- 일부 공급원 실패: 나머지 공급원으로 생성하고 오류 유형만 보고합니다.
- 공급원 전부 실패/유효한 항목 없음: 기존 XMLTV 파일을 보존합니다.
- API 키나 전체 공급원 URL은 로그에 쓰지 않습니다.
- 외부 XMLTV 제공자는 관리자가 신뢰한 주소만 등록해야 합니다.

## 현재 조사 결과와 개발 범위

2026-10-14의 Shyni 라이브 채널은 232개, 기존 EPG 연결은 47개였습니다.
MBC 본채널과 EBS2는 당시 MyEPG XMLTV에 최신 프로그램이 없었고, EBS1은 편성표가 있으나 EBS 1과 이름이 달랐습니다.

v0.1.0은 **데이터 연결 엔진**입니다. 실제 232개 채널의 편성표를 생성한다는 의미는 아닙니다.

## v0.1.3 기본 공급원 및 인증 구조

설정 DB·Git 저장소에 실제 API 키를 넣지 않도록 FF 내부 별칭을 사용합니다.

```text
FF EPGCustom 설정
 ├─ ff://alive/api/m3u       → 실행 시 ToolUtil.make_apikey_url('/alive/api/m3u')
 ├─ ff://myepg/api/epgall    → 실행 시 ToolUtil.make_apikey_url('/myepg/api/epgall')
 └─ ff://epg/api/xml/alive   → 실행 시 ToolUtil.make_apikey_url('/epg/api/xml/alive')
```

서버 주소와 인증 키는 실행 시 FF가 가진 설정을 참조하여 실제 HTTPS URL에 결합합니다. 저장된 `ff://` 주소 자체에는 비밀값이 없습니다. 사용자가 직접 지정한 HTTP(S) URL은 수정하지 않습니다.

M3U 응답의 채널 수가 0이면 생성 전 중지하고, 공급원 XMLTV의 파싱 오류 또는 0개 편성인 경우 해당 공급원만 제외합니다. 한 공급원이라도 정상 데이터가 있으면 결과를 생성하고, 보고서의 `연결진단`에 검사된 채널/프로그램 수를 기록합니다. 전체 생성에 실패하면 직전 XMLTV 파일을 유지합니다.

이 구조는 FF 내부 공개 URL에 네트워크로 접근하므로 NAS 자체에서 해당 DDNS/역방향 프록시 주소를 접근할 수 있어야 합니다. FF의 DDNS 값이 설정되지 않았거나 NAS 내부에서 접속이 차단된 경우 주소 자동 변환만으로 수집이 성공하지는 않습니다.

기본 `/alive/api/m3u`는 ALive에서 선택한 채널 목록이며, `/alive/api/m3uall`과 다릅니다. Shyni hybrid M3U는 별도로 존재하므로 최종 Shyni 적용 전에 `tvg-id`의 동일성을 검사해야 합니다.


## v0.2.1 — FF ALive + ff_iproxy2 구성으로 Shyni hybrid ID 재현

- ALive M3U에서 `KBS 1TV`, `KBS 2TV`라는 *표시 이름*의 중복 채널만 제거합니다.
- ff_iproxy2 M3U(`type=mpegts`)에 있는 채널 중 ALive에 동일 표시명이 없는 것만 추가합니다.
- 추가 채널은 Shyni hybrid와 동일하게 `tvg-name`을 ID로 사용합니다.
- 원본 229개 Alive 항목(고유 ID 218개) + iproxy2 전용 16개 - KBS 중복 2개 = Shyni와 동일한 **232개 고유 채널 ID**를 독립 검증했습니다.
- FF iproxy2가 불안정하거나 없으면 ALive M3U만 사용하여 생성하고, 진단에서 폴백을 표시합니다.
- 재생 주소 자체는 EPG 생성용 M3U에서만 처리하고 산출 XMLTV에 보관하지 않습니다.
- 기본 XMLTV 소스는 MyEPG 한 곳입니다. FF EPG 플러그인의 API는 404로 확인되어 기본 사용하지 않습니다.
- 후속 EPG 커버리지는 MyEPG에 실제 존재하는 최신 편성표 데이터와 추가적으로 검증한 XMLTV 소스에 의해 결정됩니다.


## v0.3.0 — 공급원 선택·gzip 메모리 처리·장애 파일 보존

\`\`\`text
FF ALive + ff_iproxy2  →  Shyni hybrid 호환 M3U 채널 ID
                                |
        MyEPG XMLTV ─┐         |
                     ├─ 파싱 1회 → 채널별 후보 검증 → EPGCustom XMLTV
        KR1 xml.gz ──┘            ├─ 기존 MyEPG 유효 편성 우선
          (ON일 때만)             ├─ 없는/만료된 채널만 KR1 보완
                                  └─ 정확 ID → 정확 표시명 → 명시적 별칭 → 안전 정규화
\`\`\`

- \`service/io.py\`: gzip 매직 바이트/확장자/Content-Encoding 감지, 압축 및 해제 크기를 각각 64MiB로 제한. 손상 피드는 로딩 거부.
- \`service/sources.py\`: 저장 DB URL을 덮어쓰지 않고 **MyEPG 단일 기본값 + KR1 ON일 때에만** 외부 보조 공급원을 추가. 사용자 지정 공급원에는 강제 추가하지 않음.
- \`service/core.py\`: SPOTV Prime/Prime+처럼 중요한 구분 기호 \`+\`와 \`&\`를 유지하고, 정확한 ID·표시명이 먼저 선택되도록 수정. \`prefer_primary=True\` 시 공급원 순서를 유지하고 첫 공급원의 현재 유효 편성 우선.
- \`mod_main.py\`: 별칭·정책 ON/OFF를 실행 시점에 합치고, 파싱 결과 재사용. 유효 공급원 일부 실패 시 기존 \`epgall.xml\`과 \`report.json\`이 있으면 새 파일로 덮어쓰지 않고 현재 실패 상태만 표시. 최초 생성 시 확보 가능한 공급원 결과는 \`부분 성공\`으로 표시.
- 실제 외부 KR1 소스의 최신 가용성 및 사용 조건은 FF 운영 환경에서 재확인해야 하며, KR1 서버 오류·인증 차단·다운로드 실패 시 기존 결과 보존 원칙을 유지.
