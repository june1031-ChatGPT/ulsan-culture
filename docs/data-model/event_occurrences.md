# Event occurrence 데이터 모델

`events.event_start`와 `events.event_end`는 프로그램의 대표/요약 기간으로 유지한다. 실제 검색, 달력, 행사 전 알림에서 사용할 비연속 회차는 `event_occurrences.start_at`과 `event_occurrences.end_at`을 기준으로 한다. 접수기간인 `registration_start`와 `registration_end`는 프로그램 단위이므로 occurrence에 복제하지 않는다.

대표/요약 기간 또는 접수기간이 날짜 정밀도로만 확인되면 각각 `event_start_date`/`event_end_date`, `registration_start_date`/`registration_end_date`를 사용한다. 같은 경계값의 datetime/date 컬럼은 상호 배타적이며, occurrence는 실제 회차 시각이 확인된 경우만 생성한다.

## 원본 회차 식별자

한 이벤트 안에서 `source_occurrence_id`가 유일하도록 `(event_id, source_occurrence_id)` unique constraint를 둔다. Adapter는 원본 식별자를 안정적인 문자열로 조합해야 한다.

- EXP: `rsrcUnqId + 날짜 + oprtId`
- DAY: `rsrcUnqId + 날짜 + 시작시간 + 종료시간`

동일한 원본 회차의 시간이나 예약 현황이 변경되면 새 행을 만들지 않고 이 키로 기존 행을 갱신한다.

## 정원 값의 의미와 한계

현재 `capacity`, `reserved_count`, `available_count`는 세 값이 같은 단위와 의미를 가진다는 것이 원본에서 분명할 때만 채운다. `40명`, `10팀`, `가족당 최대 4명`은 서로 다른 제약이므로 합산하거나 하나의 숫자로 축약하지 않는다. 의미가 불분명하면 정규화 필드는 `null`로 두고 XHR 응답은 `source_raw_data` JSONB에 그대로 보존한다.

울산모아 Adapter 구현 과정에서 복수 정원 제약을 검색·표시에 사용해야 한다면 다음 구조를 별도 migration으로 추가한다.

- occurrence별 복수 제약을 담는 `occurrence_capacity_constraints` 자식 테이블
- 제약 종류(전체 정원, 팀 수, 예약당 최대 인원), 값, 단위(명/팀/가족), 원문
- 예약·잔여 수치가 어떤 제약 단위를 사용하는지 나타내는 명시적 연결

이번 모델에서는 원본을 손실 없이 보존하되, 확인되지 않은 단위 간 산술 관계는 DB constraint로 강제하지 않는다.

## 누락 회차(stale) 정책

단일 페이지 수집, 상세 일부 실패, 활성 날짜별 슬롯 요청 일부 실패에서는 기존 회차를 삭제하거나 비활성화하지 않는다. 현재 upsert는 응답에서 확인한 `(event_id, source_occurrence_id)`만 insert/update하며, 이번 응답에 없다는 이유로 기존 행을 변경하지 않는다.

향후 전체 페이지 운영 수집에서 stale 처리를 추가하려면 이벤트별로 다음 조건을 모두 증명하는 수집 실행(run) 메타데이터가 먼저 필요하다.

1. 해당 Event 상세 요청이 성공했다.
2. 상세가 제시한 모든 활성 날짜의 슬롯 요청이 성공했다.
3. 응답이 차단/대기/부분 payload가 아님을 검증했다.
4. 같은 수집 run 안에서 해당 Event의 회차 집합이 완전하다고 표시됐다.

Event 수준에는 `crawl_runs`, `last_seen_at`, `last_seen_run_id`, `is_active`와 완전 스냅샷 gate를 도입했다. 자세한 정책은 `docs/data-model/crawl_runs.md`를 따른다. occurrence 수준 stale은 여전히 구현하지 않았으며, 향후에도 위 조건에 더해 해당 Event의 상세와 모든 활성 날짜 slot 응답이 완전하다는 증거가 있을 때만 별도 상태 필드와 migration으로 도입한다. 물리 삭제는 감사와 장애 복구를 어렵게 하므로 기본 정책으로 사용하지 않는다.
