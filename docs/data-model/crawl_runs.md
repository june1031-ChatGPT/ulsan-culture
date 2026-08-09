# Crawl Run과 Event 원문/last-seen 정책

## 역할 분리

`sources`의 `last_checked_at`, `last_success_at`, `last_item_count`,
`error_count`, `error_message`는 해당 Source의 현재 운영 상태 요약이다.

`crawl_runs`는 개별 실행의 시작·종료, 범위, 성공/실패 통계와 완전 스냅샷
여부를 보존한다. Source 요약을 실행 이력 대신 사용하지 않는다.

## `crawl_runs`

- 식별/범위: `id`, `source_id`, `scope`
- 시간/상태: `started_at`, `finished_at`, `status`, `created_at`
- 페이지: `pages_attempted`, `pages_succeeded`
- 항목: `items_seen`, `items_persisted`, `items_failed`
- 상세/회차: `detail_success_count`, `detail_failure_count`, `occurrence_count`
- 오류: `network_error_count`, `parser_error_count`, `error_message`
- 안전성: `is_complete_snapshot`
- 확장 요약: `summary` JSONB

`status`는 `running`, `success`, `partial`, `failed`만 허용한다. 단일 페이지
수집은 그 범위에서 오류 없이 끝나면 `success`일 수 있지만 항상
`is_complete_snapshot=false`다.

전체 수집은 다음 조건을 모두 만족할 때만 `success`이면서
`is_complete_snapshot=true`가 된다.

1. 자연 종료(마지막 pagination 또는 `cards < pageSize`)를 확인했다.
2. 시도한 모든 list page가 성공했다.
3. pagination 현재 페이지가 요청 page와 일치했다.
4. list/detail/slot network 및 parser 오류가 없다.
5. persistence 오류가 없다.
6. `max_pages` 안전 한도에 걸리지 않았다.

## Event 원문과 last-seen

Event는 정규화 값과 별개로 `registration_period_text`,
`event_period_text`, `capacity_text`, `fee_text`를 보존한다. 따라서 `상시`,
`10팀`, `가족당 최대 4명`, `회차별 상이`를 숫자나 임의 날짜로 왜곡하지
않는다.

`last_seen_at`은 운영 쿼리를 위한 최근 확인 시각이고 `last_seen_run_id`는 그
확인의 실행 근거다. 항목을 실제 list에서 확인하면 둘을 함께 갱신한다.
내부 detail이 실패한 기존 Event는 좋은 상세 필드를 null로 덮지 않고
last-seen만 갱신한다.

울산모아 한 Source에는 F300/F400이 같이 있으므로 Event의 `source_code`를
보존한다. 이는 중복 표시용이 아니라 stale 범위를 격리하기 위한 필드다.
`resource_kind`는 `source_event_id` 접두사와 adapter 중간 모델로 충분하므로
Event DB에는 추가하지 않는다.

## stale 게이트

`deactivate_stale_events()`는 다음 조건을 모두 만족하지 않으면 예외를 내고
아무 Event도 변경하지 않는다.

- run이 종료됨
- `status=success`
- `is_complete_snapshot=true`
- scope가 정확한 전체 목록 범위(`F300`, `F400`, `F300:F400`, `full`)

허용된 경우에도 동일 Source·동일 `source_code` 중 현재 run에서 보지 못한
Event만 `is_active=false`로 바꾼다. 물리 DELETE는 하지 않는다. legacy
Event처럼 `source_code`가 null인 행도 자동 비활성화하지 않는다.

## 페이지네이션과 요청 안전장치

전체 순회는 1-based `pageNo`, `pageSize=12`, 서버 렌더링 pagination의 다음
링크와 카드 수를 함께 사용한다. 총건수 위젯 값은 종료 조건으로 사용하지
않는다. 동시성은 client에서 1~2로 제한하며 timeout, retry, exponential
backoff, jitter를 적용한다. 전체 순회에는 page 사이 delay, detail/slot 요청
delay, 기본 `max_pages=500`, 상세당 활성 날짜 `31`개 한도를 적용한다.

목록 정보만으로 상세 변경이 없다고 증명할 수 없으므로 현재는 기존 ID나
목록 일부가 같다는 이유로 detail 요청을 생략하지 않는다. `content_hash`는
완성된 detail/occurrence 정규화 결과의 변경 감지 기반으로만 유지한다.
