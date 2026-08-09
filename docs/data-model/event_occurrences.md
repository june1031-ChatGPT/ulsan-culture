# Event occurrence 데이터 모델

`events.event_start`와 `events.event_end`는 프로그램의 대표/요약 기간으로 유지한다. 실제 검색, 달력, 행사 전 알림에서 사용할 비연속 회차는 `event_occurrences.start_at`과 `event_occurrences.end_at`을 기준으로 한다. 접수기간인 `registration_start`와 `registration_end`는 프로그램 단위이므로 occurrence에 복제하지 않는다.

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
