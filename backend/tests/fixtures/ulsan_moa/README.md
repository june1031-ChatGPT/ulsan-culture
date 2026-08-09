# 울산모아 parser fixture

- 수집일: 2026-08-09 (Asia/Seoul)
- 목적: 네트워크 없이 울산모아 목록·상세·시간 슬롯 parser를 재현하고 구조 변경을 감지한다.
- 요청 수: 공개 응답 7건(목록 GET 2, 상세 GET 3, 시간 슬롯 POST 2)
- 제외: 로그인, 예약, 결제, `expSelectDateCheck.do`, `dailySelectDateCheck.do`
- 정리: 응답 헤더와 쿠키는 저장하지 않았으며 HTML URL의 실제 `;jsessionid` 값은 제거했다.

## 원본 요청

| 파일 | 공개 요청 |
|---|---|
| `f300_list.html` | `GET /y/yes/page.do?mnu_code=F300&step=gallery&orderBy=rcept&pageNo=1&pageSize=12` |
| `f400_list.html` | `GET /y/yes/page.do?mnu_code=F400&step=list_img&orderBy=rcept&pageNo=1&pageSize=12` |
| `lec_detail.html` | `GET /y/yes/page.do?mnu_code=F303&step=step01&rsrcUnqId=LEC_0000000000000828` |
| `exp_detail.html` | `GET /y/yes/page.do?mnu_code=F401&step=step01&rsrcUnqId=EXP_0000000000000050` |
| `day_detail.html` | `GET /y/yes/page.do?mnu_code=F601&step=step01&rsrcUnqId=DAY_0000000000000000` |
| `exp_time_slots.json` | `POST /y/common/func/ajax/expSelectTimeList.do` with `rsrcUnqId=EXP_0000000000000050`, `rsrcYmd=2026-08-11`, `mnu_code=F401` |
| `day_time_slots.json` | `POST /y/common/func/ajax/dailySelectTimeList.do` with `rsrcUnqId=DAY_0000000000000000`, `rsrcYmd=2026-08-10`, `mnu_code=F601` |

`test_ulsan_moa_parser.py`는 fixture에 `;jsessionid`가 남아 있지 않은지 확인하고,
별도의 합성 URL로 canonical URL 세션 제거 규칙을 검증한다.
