# 울산모아 통합예약 데이터 구조 조사

- 조사일: 2026-08-09 (Asia/Seoul)
- 공식 사이트: <https://ulsan.go.kr/y/yes/main.do>
- 범위: 교육강좌, 문화체험, 상시체험의 공개 목록·상세와 화면에서 실제 사용하는 JSON/XHR
- 제외: 로그인, 예약 제출, 결제, 전체 페이지 순회, 크롤러 구현, Playwright

## 결론

가장 권장되는 수집 방식은 **서버 렌더링 목록/상세 HTML + 내부 체험의 시간 슬롯 JSON/XHR 보강**이다.

울산모아에는 행사 전체를 반환하는 공개 API나 목록/상세 JSON API가 이번 조사 범위에서 확인되지 않았다. 교육강좌와 문화체험 목록은 JavaScript 렌더링 없이 `GET /y/yes/page.do`의 정적 HTML로 내려오며, 내부 상세도 같은 방식이다. 따라서 Playwright는 필요하지 않다.

수집 진입점은 하위 메뉴를 각각 순회하기보다 다음 두 전체 목록을 우선 사용하는 것이 단순하고 안정적이다.

1. 교육강좌 전체: `mnu_code=F300`
2. 문화체험 전체: `mnu_code=F400` (교육체험·문화행사·전시/관람·상시체험 포함)

다만 문화체험 전체 목록에는 울산모아 내부 예약 건과 외부기관 연계 건이 섞여 있다. 내부 건은 `LEC_...`, `EXP_...`, `DAY_...` 자원 ID로 상세 데이터를 보강할 수 있다. 외부 건은 울산모아 목록 카드의 제한된 정보만 저장하고, 외부 상세를 수집하려면 해당 기관을 별도 Source/Adapter로 취급해야 한다.

## 1. 공식 사이트 구조

기본 호스트는 `https://ulsan.go.kr`이다. `https://www.ulsan.go.kr` 요청은 비-www 호스트로 리다이렉트될 수 있다. 특히 POST XHR은 리다이렉트 과정에서 본문이 유실될 수 있으므로 처음부터 비-www 호스트를 사용해야 한다.

| 영역 | 전체 코드 | 하위 코드 |
|---|---:|---|
| 교육강좌 | `F300` | `F301` 스포츠, `F302` 생활/취미, `F303` 역사/과학/도서, `F304` 외국어, `F306` 전문/자격증, `F309` AI, `F399` 기타 |
| 문화체험 | `F400` | `F401` 교육체험, `F402` 문화행사, `F403` 전시/관람, `F601` 상시체험 |

2026-08-09 표본 확인 시 전체 게시물 수는 교육강좌 `2,692`, 문화체험 `666`, 교육체험 `129`, 상시체험 `4`였다. 이 수치는 계속 변하므로 구현 상수로 사용하지 않는다.

내부 자원 ID 접두사는 다음과 같이 확인했다.

| 접두사 | 의미 | 상세 형태 |
|---|---|---|
| `LEC_` | 교육강좌 | 정적 상세 HTML |
| `EXP_` | 날짜 선택형 교육/문화체험 | 정적 상세 HTML + 날짜별 시간 슬롯 XHR |
| `DAY_` | 상시체험 | 정적 상세 HTML + 날짜별 시간 슬롯 XHR |

## 2. robots.txt 및 이용정책

### robots.txt

실제 확인 URL: <https://ulsan.go.kr/robots.txt>

2026-08-09 요청은 `200 OK`였고 내용은 다음과 같았다.

```text
User-agent: *
Disallow: /u/hhmgr01/*
Disallow: /s/hhmgr02/*
Allow: /
```

`/y/yes/`는 robots.txt에서 차단하지 않는다. robots 허용은 저작권이나 이용약관상 재이용 허락을 의미하지 않는다.

### 이용약관·저작권

- [울산광역시 이용약관](https://www.ulsan.go.kr/u/rep/contents.ulsan?mId=001005008008000000)은 시청의 사전 승낙 없는 서비스 이용 영리행위를 금지한다.
- [울산광역시 저작권보호 정책](https://www.ulsan.go.kr/u/rep/contents.ulsan?mId=001005008003000000)은 공공누리 표시가 있는 자료는 해당 유형 조건에 따라 이용할 수 있으나, 공공누리 표시가 없는 자료는 담당부서와 사전 협의하도록 안내한다.
- 울산모아 푸터는 전자우편주소 무단 수집을 거부하며 [개인정보처리방침](https://www.ulsan.go.kr/u/rep/contents.ulsan?mId=001005008001000000)을 연결한다.

구조화된 사실 메타데이터와 공식 링크를 중심으로 수집하고, 상세 설명 전문이나 이미지는 라이선스 확인 없이 복제·재배포하지 않는 편이 안전하다. 특히 외부 연계 항목 이미지는 제3자 도메인 저작물이다. 서비스가 영리 목적이라면 운영 전 울산광역시 담당부서에 수집·재이용 범위를 확인해야 한다.

## 3. 수집 우선순위별 조사 결과

| 우선순위 | 결과 | 판단 |
|---|---|---|
| 공개 API | 공개 문서나 행사 목록/상세 API를 확인하지 못함 | 사용하지 않음 |
| JSON/XHR | 기관 통계·기관 목록·내부 체험 시간 슬롯용 Endpoint 확인 | 시간/정원 보강에 제한적으로 사용 |
| RSS/XML | 목록 페이지, 페이지 소스, 공식 검색 범위에서 피드 링크를 확인하지 못함 | 사용하지 않음 |
| 정적 HTML | 전체 목록, 페이지네이션, 내부 상세가 서버 렌더링됨 | 주 수집 방식 |
| Playwright | 불필요 | 사용하지 않음 |
| PDF/OCR | 이 소스의 기본 목록/상세 수집에는 불필요 | 사용하지 않음 |

## 4. 목록 페이지

### URL과 method

```http
GET https://ulsan.go.kr/y/yes/page.do
```

교육강좌 예:

```text
https://ulsan.go.kr/y/yes/page.do?mnu_code=F300&step=gallery&orderBy=rcept&pageNo=1&pageSize=12
```

문화체험 예:

```text
https://ulsan.go.kr/y/yes/page.do?mnu_code=F400&step=list_img&orderBy=rcept&pageNo=1&pageSize=12
```

### 파라미터

| 파라미터 | 필수 여부 | 확인값/의미 |
|---|---|---|
| `mnu_code` | 필수 | 전체는 `F300`, `F400`; 하위 분류 코드도 가능 |
| `step` | 권장 | 교육 `gallery`, 문화체험 `list_img`; 목록형 화면은 `list` |
| `orderBy` | 권장 | `rcept` 추천순, `use` 이용기간 순, `org` 지역명 순, `rsrc` 장소명 순 |
| `pageNo` | 필수 | 1부터 시작. `pageNo=2`가 실제로 현재 2페이지 HTML을 반환함 |
| `pageSize` | 권장 | 화면 기본값 `12` |
| `city` | 선택 | 빈 값 전체, `N` 남구, `J` 중구, `B` 북구, `D` 동구, `U` 울주군 |
| `srchSe` | 선택 | `all`, `orgNm`, `svc`, `place` (`svc`는 교육에서 강좌명, 문화에서 자원명) |
| `srchKwd` | 선택 | 검색어 |
| `rsrcClCd` | 선택 | 하위 분류 페이지의 페이지네이션 링크에 하위 `mnu_code`와 같은 값으로 나타남. 전체 목록에서는 불필요 |

응답은 `text/html; charset=utf-8`이며 카드 목록과 페이지네이션이 HTML에 완성된 상태다. 목록 페이지 소스에서는 행사 목록을 가져오는 AJAX/fetch 호출이 없었다.

### 페이지네이션

- 1-based `pageNo`
- 기본 `pageSize=12`
- 페이지 링크가 다음 요청 URL을 직접 제공함
- 10페이지 단위의 다음 묶음 링크가 있음
- 종료 조건은 마지막 페이지 링크 또는 현재 페이지 카드 수가 `pageSize`보다 작은 경우로 잡을 수 있음

### 카드에서 얻을 수 있는 값

교육강좌 카드:

- 기관/장소 표기
- 제목
- 접수상태
- 신청방식(온라인/현장/전화/외부사이트)
- 접수기간(날짜만)
- 강좌기간(날짜만)
- 모집정원
- 무료/유료
- 분류
- 상세 또는 외부 링크
- 이미지 URL

문화체험 카드:

- 기관/장소 표기
- 제목
- 접수상태
- 신청방식
- 접수기간(날짜만)
- 장소
- 무료/유료
- 시설종류와 분류
- 상세 또는 외부 링크
- 이미지 URL

문화체험 카드는 일반적으로 실제 행사/이용기간을 제공하지 않는다. 내부 체험은 상세의 달력/XHR로 보강해야 하고, 외부 연계 항목은 외부 상세 없이는 `event_start`, `event_end`를 확정할 수 없다.

## 5. 상세 페이지

### 내부 상세 URL

```http
GET https://ulsan.go.kr/y/yes/page.do?mnu_code={subcategory}&step=step01&rsrcUnqId={resource_id}
```

검증 예:

- 교육강좌: `mnu_code=F303`, `rsrcUnqId=LEC_0000000000000828`
- 교육체험: `mnu_code=F401`, `rsrcUnqId=EXP_0000000000000050`
- 상시체험: `mnu_code=F601`, `rsrcUnqId=DAY_0000000000000000`

URL 안의 `;jsessionid=...`는 세션별 임시 값이다. 저장 URL, 중복 키, content hash를 만들 때 반드시 제거한다.

### `LEC_` 교육강좌 상세

샘플 상세의 요약 영역에서 다음 값을 직접 확인했다.

```text
기관: 울산대곡박물관
제목: 과학으로 배우는 문화유산 (유물 복원 체험) - 8월 13일(목)
대상: 제한없음
장소명: 울산대곡박물관
접수기간: 2026-07-01 09:00 ~ 2026-08-10 17:00
강좌기간: 2026-08-13 10:30 ~ 2026-08-13 12:00
예약방법: 인터넷
요금: 무료
접수현황: 14 / 20
대기현황: 0 / 5
```

`강좌기간`이 행사기간이고 `접수기간`이 신청기간이다. 상세 HTML에는 일반 목록 API나 상세 JSON API를 호출하는 XHR이 없었다.

예약 버튼은 `step=step02`로 POST하고 `rsrcUnqId`를 전달한다. 로그인/세션이 필요한 흐름이므로 수집 서비스의 `reservation_url`은 POST 주소를 흉내 내지 말고 사용자가 정상적으로 진입할 수 있는 공개 `step01` 상세 URL을 쓰는 것이 안전하다.

### `EXP_` 날짜 선택형 체험 상세

요약 영역에는 제목, 대상, 접수기간, 장소, 이용요금, 예약방법, 문의전화가 있다. 행사일은 요약에 단일 기간으로 나오지 않고 달력의 선택 가능 날짜와 날짜별 XHR 슬롯으로 제공된다.

검증 샘플:

```text
제목: 가족 아트워크숍
기관: 울산시립미술관
대상(요약): 단체
접수기간: 2026-08-03 10:00 ~ 2026-08-10 17:00
장소: 울산 중구 미술관길 72울산시립미술관
이용요금: 무료
예약방법: 인터넷
```

설명 원문에는 `6세 이상 어린이를 포함한 가족 10팀`처럼 요약의 `대상: 단체`보다 구체적인 조건이 있었다. 따라서 `target_text`는 요약값만 믿지 말고 상세 설명의 대상/참여 기준 원문도 함께 보존해야 한다.

달력에는 2026-08-11, 12, 13, 17, 19가 선택 가능 날짜로 렌더링되었고, 설명의 워크숍 일시와 일치했다. 날짜별 XHR이 시작/종료시각과 정원을 반환한다.

### `DAY_` 상시체험 상세

샘플 요약:

```text
제목: 어린이 박물관(이용시간 50분)
기관: 울산박물관
대상: 제한없음
접수기간: 상시
장소: 울산 남구 두왕로 277울산박물관
이용요금: 무료
예약방법: 인터넷, 방문
```

`접수기간: 상시`는 특정 시작/종료시각이 아니므로 `registration_start`, `registration_end`를 임의의 날짜로 만들지 않는다. 실제 이용 가능일과 회차는 DAY 전용 시간 슬롯 XHR에서 얻는다.

### 외부 연계 상세

`target="_blank"`이며 링크가 `ulsan.go.kr/y/yes/page.do`가 아닌 카드는 울산모아 내부 상세가 없다. 예를 들어 HD아트센터, 교육청, 구·군 예약시스템, 문화예술회관 상세로 바로 이동한다.

이 경우:

- 울산모아 카드가 제공한 제목·기관·접수기간·강좌기간(교육만)·요금·이미지·외부 URL은 수집 가능
- 울산모아 `rsrcUnqId`는 HTML에 노출되지 않음
- 외부 URL의 provider ID는 울산모아 ID가 아님
- 주소, 대상, 상세 행사일(문화체험), 정확한 요금, 정원은 외부 Source Adapter가 필요

## 6. 실제 검증한 JSON/XHR Endpoint

모든 POST는 `application/x-www-form-urlencoded`로 검증했으며, 응답 Content-Type은 `application/json;charset=UTF-8`이었다.

### 6.1 지역별 건수

```http
POST https://ulsan.go.kr/y/common/func/widget/selectCityStats.do
dataDivCd=F400
```

샘플 응답:

```json
[
  {"city":"U","cityNm":"울주군","totalCnt":157},
  {"city":"N","cityNm":"남구","totalCnt":290},
  {"city":"J","cityNm":"중구","totalCnt":2},
  {"city":"B","cityNm":"북구","totalCnt":81},
  {"city":"D","cityNm":"동구","totalCnt":132}
]
```

이 Endpoint는 행사 목록이 아니라 메인 위젯용 집계다. 표본 시 합계 `662`는 문화체험 전체 목록의 `666`과 달랐으므로 전체 수집 종료조건이나 정합성 기준으로 사용하지 않는다. 지역 미지정 항목 또는 갱신 시차 가능성이 있다.

`dataDivCd`는 화면 코드에서 `F300`, `F400`, `F100`, `F200`을 확인했다. 이번 목적에는 `F300`, `F400`만 필요하다.

### 6.2 기관 목록

```http
POST https://ulsan.go.kr/y/common/func/widget/selectOrgList.do
city=N
dataDivCd=F400
```

샘플 응답:

```json
[
  {"orgUnqId":"LNKORG_0000000000016","orgNm":"울산과학관","rsrcCnt":50},
  {"orgUnqId":"LNKORG_0000000000011","orgNm":"울산문화예술회관","rsrcCnt":240},
  {"orgUnqId":"ORG_0000000000000014","orgNm":"울산박물관","rsrcCnt":2}
]
```

`city`는 빈 값 또는 `N/J/B/D/U`다. 이것도 탐색/기관 메타데이터 보조용이며 행사 목록 API가 아니다.

### 6.3 `EXP_` 날짜별 시간 슬롯

```http
POST https://ulsan.go.kr/y/common/func/ajax/expSelectTimeList.do
rsrcUnqId=EXP_0000000000000050
rsrcYmd=2026-08-11
mnu_code=F401
```

샘플 응답:

```json
[
  {
    "oprtId": 326,
    "stTm": "10:00",
    "enTm": "12:00",
    "aplyYn": "Y",
    "useLmtNmpr": 40,
    "maxPer": 4,
    "rsvCnt": 17,
    "useTrgt": "G"
  }
]
```

`rsrcYmd`는 상세 달력의 `data-date` 값(`YYYY-MM-DD`)을 그대로 사용한다. 달력에서 활성화된 날짜에 대해서만 요청해야 한다.

### 6.4 `EXP_` 선택 회차 확인

```http
POST https://ulsan.go.kr/y/common/func/ajax/expSelectDateCheck.do
oprtId=326
mnu_code=F401
```

샘플 응답:

```json
{
  "result": true,
  "msg": "",
  "data": {
    "APLY_NMPR": 4,
    "USE_YMD": "2026-08-11",
    "RSV_CNT": 17,
    "FREE_YN": "Y",
    "USE_LMT_NMPR": 40,
    "FEE": 0,
    "USE_TRGT": "G",
    "ORG_UNQ_ID": "ORG_0000000000000019",
    "OPRT_ID": 326,
    "MAX_PER": 4,
    "ST_TM": "10:00",
    "EN_TM": "12:00"
  }
}
```

시간 슬롯 응답과 중복되는 예약 직전 검증 성격의 Endpoint다. 일반 수집에서는 `expSelectTimeList.do`만으로 충분하므로 이 Endpoint를 반복 호출하지 않는 것을 권장한다.

### 6.5 `DAY_` 날짜별 시간 슬롯

```http
POST https://ulsan.go.kr/y/common/func/ajax/dailySelectTimeList.do
rsrcUnqId=DAY_0000000000000000
rsrcYmd=2026-08-10
mnu_code=F601
```

샘플 응답의 첫 원소:

```json
{
  "stTm": "09:30",
  "enTm": "10:30",
  "aplyYn": "N",
  "fee": null,
  "lmtNmpr": 50,
  "curNope": 50
}
```

같은 날짜에 09:30부터 16:30까지 7개 회차가 반환되었다.

### 6.6 `DAY_` 선택 회차 확인

```http
POST https://ulsan.go.kr/y/common/func/ajax/dailySelectDateCheck.do
rsrcUnqId=DAY_0000000000000000
rsrcYmd=2026-08-10
timeRange=09:30-10:30
mnu_code=F601
```

검증한 회차가 만석인 상태여서 다음 응답을 받았다.

```json
{"result":false,"msg":"이미 예약된 시간과 겹칩니다."}
```

클라이언트 코드상 성공 응답에서는 `useStTm`, `useEnTm`, `sumFee`를 사용하지만 이번 표본에서는 성공 구조를 실제 확인하지 못했다. 이 Endpoint 역시 예약 직전 확인 성격이므로 정기 수집에 사용하지 않는 것을 권장한다.

## 7. 샘플 필드 매핑

| 목표 필드 | 내부 `LEC_` | 내부 `EXP_`/`DAY_` | 외부 연계 카드 | 판단/주의 |
|---|---|---|---|---|
| `title` | 상세 제목 또는 카드 `h4.tit` | 상세 제목 또는 카드 `h4.tit` | 카드 `h4.tit` | 가능 |
| `organizer` | 상세 상단 기관명 | 상세 상단 기관명 | 카드 `p.place` | 가능하나 외부 카드에서는 기관/장소 의미가 섞일 수 있음 |
| `venue` | `장소명` | `장소` | 카드 `장소`/`p.place` | 가능 |
| `address` | 장소안내 탭 `주소` | 장소안내 탭 `주소` | 없음 | 내부도 빈 값일 수 있고 주소와 시설명이 붙어 나올 수 있음 |
| `target_text` | `대상` + 설명의 참가대상 원문 | `대상` + 설명의 참여대상/기준 원문 | 없음 | 요약보다 설명이 정확할 수 있으므로 둘 다 보존 |
| `event_start` | `강좌기간` 시작 | 활성 날짜 + 슬롯 `stTm` | 교육 카드는 강좌기간 날짜, 문화 카드는 없음 | 상세/XHR 우선 |
| `event_end` | `강좌기간` 종료 | 활성 날짜 + 슬롯 `enTm` | 교육 카드는 강좌기간 날짜, 문화 카드는 없음 | 다회차는 occurrence 모델 필요 |
| `registration_start` | `접수기간` 시작 | `접수기간` 시작 | 카드 `접수기간` 시작 | 상세에 시간이 있으면 상세 우선 |
| `registration_end` | `접수기간` 종료 | `접수기간` 종료 | 카드 `접수기간` 종료 | `상시`/빈 값은 `null` + 원문 보존 |
| `fee` | `요금` | `이용요금`, 슬롯의 `fee`/`FEE` 보조 | 무료/유료만 | 가능한 범위에서 가능 |
| `capacity` | `접수현황`의 분모 또는 카드 `모집정원` | `useLmtNmpr`/`lmtNmpr` | 교육 카드 정원, 문화 카드는 대체로 없음 | 팀 수와 인원 수를 혼용하지 말 것 |
| `reservation_url` | 공개 `step01` 상세 URL | 공개 `step01` 상세 URL | 외부 href | 내부 예약은 POST/login이므로 상세 URL을 진입점으로 사용 |
| `detail_url` | canonical `step01` URL | canonical `step01` URL | 외부 href | `;jsessionid` 제거 |
| `image_url` | 상세/카드 `img[src]` | 상세/카드 `img[src]` | 카드의 외부 이미지 URL | 저장은 가능하나 재배포 권한은 별도 확인 |
| `source_event_id` | `rsrcUnqId` (`LEC_...`) | `rsrcUnqId` (`EXP_...`/`DAY_...`) | `null` | Source가 공식 제공한 ID만 저장 |
| `source_item_key` | `source_event_id`와 동일 | `source_event_id`와 동일 | `urlsha256:<canonical URL의 SHA-256>` | 울산컬처 내부 식별키. `(source_id, source_item_key)`로 유일 |

### 샘플 핵심 매핑

교육강좌 `LEC_0000000000000828`:

```text
title                = 과학으로 배우는 문화유산 (유물 복원 체험) - 8월 13일(목)
organizer            = 울산대곡박물관
venue                = 울산대곡박물관
address              = null (이 표본의 장소안내 주소가 비어 있음)
target_text          = 제한없음 + 설명의 "6세 이상 ~ 초등학생 개인 및 단체"
event_start          = 2026-08-13 10:30
event_end            = 2026-08-13 12:00
registration_start   = 2026-07-01 09:00
registration_end     = 2026-08-10 17:00
fee                  = 무료
capacity             = 20
reservation_url      = https://ulsan.go.kr/y/yes/page.do?mnu_code=F303&step=step01&rsrcUnqId=LEC_0000000000000828
detail_url           = https://ulsan.go.kr/y/yes/page.do?mnu_code=F303&step=step01&rsrcUnqId=LEC_0000000000000828
image_url            = https://ulsan.go.kr/y/common/func/atch/ImageView.do?atchFileId=FILE_000000000003053&fileSn=0
source_event_id      = LEC_0000000000000828
source_item_key      = LEC_0000000000000828
```

교육체험 `EXP_0000000000000050`의 2026-08-11 회차:

```text
title                = 가족 아트워크숍
organizer            = 울산시립미술관
venue                = 울산시립미술관
address              = 울산 중구 미술관길 72울산시립미술관 (원문)
target_text          = 단체 + 설명의 "6세 이상 어린이를 포함한 가족 10팀"
event_start          = 2026-08-11 10:00
event_end            = 2026-08-11 12:00
registration_start   = 2026-08-03 10:00
registration_end     = 2026-08-10 17:00
fee                  = 무료
capacity             = 40명 (XHR), 설명에는 10팀/가족당 최대 4명
reservation_url      = https://ulsan.go.kr/y/yes/page.do?mnu_code=F401&step=step01&rsrcUnqId=EXP_0000000000000050
detail_url           = https://ulsan.go.kr/y/yes/page.do?mnu_code=F401&step=step01&rsrcUnqId=EXP_0000000000000050
image_url            = https://ulsan.go.kr/y/common/func/atch/ImageView.do?atchFileId=FILE_000000000004042&fileSn=0
source_event_id      = EXP_0000000000000050
source_item_key      = EXP_0000000000000050
```

## 8. 행사일과 접수일의 명확한 구분

다음 규칙을 고정해야 한다.

| 원본 라벨/값 | 저장 필드 |
|---|---|
| `접수기간` | `registration_start`, `registration_end` |
| `강좌기간` | `event_start`, `event_end` |
| EXP/DAY 달력 활성 날짜 + 슬롯 `stTm`/`enTm` | 행사 occurrence의 시작/종료 |
| 설명의 `일시`, `교육시간` | 검증/보완 원문. 구조화 값과 충돌하면 경고 |
| 카드의 접수기간 | 상세 접수시간이 없을 때만 날짜 정밀도로 사용 |

특히 다음을 피한다.

- 목록의 접수기간을 행사기간으로 저장하지 않기
- 날짜만 있는 목록값에 임의로 `00:00`/`23:59:59`를 붙이지 않기
- `접수기간: 상시`를 임의의 무한 날짜로 변환하지 않기
- 여러 체험 회차의 최소~최대만 저장해 그 사이가 계속 운영되는 것처럼 보이게 하지 않기

날짜만 확인한 값은 `event_start_date`/`event_end_date` 또는 `registration_start_date`/`registration_end_date`에 저장한다. 시각까지 확인한 값은 기존 datetime 필드에 저장하며 대응 date 필드는 `null`로 둔다.

여러 비연속 회차는 `event_occurrences`에 보존한다. 대표 이벤트에는 요약 기간을 둘 수 있지만, 실제 알림·달력은 occurrence를 기준으로 해야 한다.

## 9. 구현 시 주의사항

1. **Playwright 불필요**: 목록과 상세가 서버 렌더링되며 필요한 시간 슬롯만 JSON이다.
2. **내부/외부 링크 분기**: 같은 목록에서 내부 자원과 외부기관 링크가 섞인다. 외부 상세를 울산모아 DOM 규칙으로 파싱하면 안 된다.
3. **세션 ID 제거**: URL과 HTML에 `;jsessionid=...`가 삽입된다. canonical URL, 중복키, hash에서 제거한다.
4. **비-www 호스트 사용**: POST 리다이렉트에 따른 본문 유실을 막는다.
5. **시간 슬롯 요청 최소화**: 상세 달력에서 활성화된 날짜에만 `*SelectTimeList.do`를 호출한다. `*SelectDateCheck.do`는 정기 수집에 불필요하다.
6. **다회차 보존**: EXP/DAY는 한 자원에 여러 날짜·시간 슬롯이 있다.
7. **정원 단위 보존**: `40명`, `10팀`, `가족당 4명`은 서로 다른 값이다. 원문/단위를 함께 보존한다.
8. **대상 원문 보존**: 요약의 `단체`, `제한없음`이 실제 설명과 다를 수 있다.
9. **주소 정규화 주의**: 주소와 시설명이 구분자 없이 연결된 사례가 있다.
10. **날짜 정밀도 보존**: 목록은 날짜, 상세는 시각까지 제공한다. 상세 우선이며 불명 시각을 생성하지 않는다.
11. **응답 캐시**: 목록 응답에서는 `ETag`, `Last-Modified`, `Cache-Control`을 확인하지 못했다. `content_hash`로 변경 여부를 판단한다. robots.txt에는 ETag/Last-Modified가 있었다.
12. **대기/차단 페이지 감지**: 사이트는 TRACER 대기·차단 문구를 HTML에 포함할 수 있다. HTTP 200만 성공으로 판단하지 말고 제목/본문 시그니처와 기대 카드 컨테이너를 검증한다.
13. **요청 간격과 재시도**: 낮은 동시성, timeout, 지수 백오프, jitter를 사용한다. 전체 목록을 매번 상세까지 전부 재요청하지 말고 목록 hash와 기존 ID를 비교한다.
14. **이미지 정책**: 이미지 URL 수집과 이미지 파일 재배포는 별개다. 공공누리/권리 확인 전에는 원본 URL과 출처만 보존하는 것이 안전하다.
15. **상태는 날짜/시각에서 계산**: 화면의 `접수중`, `접수마감` 표시는 원문으로 보존하되 내부 상태는 접수 시작/종료의 확인된 정밀도에 따라 계산한다.

## 10. 권장 수집 흐름

아직 구현하지 않은 설계 제안이다.

```text
F300/F400 전체 목록 GET
→ 카드 파싱 및 canonical URL 생성
→ 내부 LEC/EXP/DAY와 외부 링크 분리
→ 신규/변경 내부 상세만 GET
→ LEC는 상세 HTML로 완료
→ EXP/DAY는 활성 달력 날짜만 시간 슬롯 JSON POST
→ 원문과 occurrence를 보존하여 normalize
→ 외부 링크는 울산모아 카드 수준으로 저장하고 별도 Source 후보로 큐잉
```

목록 수집은 `orderBy=rcept`의 순위가 바뀔 수 있으므로 ID 기반으로 upsert한다. 종료된 항목이 목록 후반으로 이동하거나 전체 건수가 변할 수 있으므로 한 번의 부분 페이지 수집 결과만으로 기존 데이터를 삭제하지 않는다.

## 11. 다음 작업 제안

1. `event_occurrences`/회차 모델을 먼저 결정한다.
2. 울산모아 Adapter의 fixture를 만들기 위해 다음 최소 응답만 저장한다: F300 목록 1페이지, F400 목록 1페이지, LEC/EXP/DAY 상세 각 1건, EXP/DAY 슬롯 JSON 각 1건.
3. parser 단위 테스트를 먼저 작성한다. 검증 항목은 세션 ID 제거, 접수/행사기간 분리, 내부/외부 링크 분기, 다회차, 상시 접수, 정원 단위다.
4. 그 다음에만 `fetch_list()`/`fetch_detail()`을 구현한다. Playwright 의존성은 추가하지 않는다.
5. 외부 연계 비중이 큰 기관은 울산모아와 별도로 Source 우선순위를 정한다. 울산과학관, 교육청, 문화예술회관, 구·군 예약시스템이 후보이다.
6. 운영 전 울산광역시에 자동수집 주기, 메타데이터 재이용, 이미지 표시 범위를 문의한다.

## 검증한 공식 URL

- 메인: <https://ulsan.go.kr/y/yes/main.do>
- 교육강좌 전체: <https://ulsan.go.kr/y/yes/page.do?mnu_code=F300>
- 문화체험 전체: <https://ulsan.go.kr/y/yes/page.do?mnu_code=F400>
- 교육체험: <https://ulsan.go.kr/y/yes/page.do?mnu_code=F401>
- 상시체험: <https://ulsan.go.kr/y/yes/page.do?mnu_code=F601>
- robots.txt: <https://ulsan.go.kr/robots.txt>

이번 문서는 구조 조사 결과이며 크롤러 코드는 구현하지 않았다.
