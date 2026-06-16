---
name: project-data-adapter-security
description: Tiingo/EODHD 어댑터 토큰 비노출 규약과 미해결 httpx 로거 부채
metadata:
  type: project
---

가격 데이터 어댑터(`src/stockpick/data/{tiingo,eodhd}.py`)의 토큰 누출 방어 상태(2026-06-16 리뷰):

- 토큰은 호출 시점 `os.environ` 에서 읽고 로그·예외·repr 어디에도 안 남김(테스트로 검증: `test_*_never_appears_in_exceptions_or_repr`).
- Tiingo: `Authorization: Token <KEY>` 헤더 인증 → URL 에 토큰 없음. 예외는 path/ticker 만.
- EODHD: `?api_token=<KEY>` **쿼리** 인증 → 완성 URL 에 토큰 실림. 어댑터는 `from None` 으로 httpx 예외 체인을 끊어 토큰 실린 URL 누출을 막음.

**미해결 부채:** EODHD 사용 시 `httpx._client` 라이브러리 INFO 로거가 토큰 실린 완성 URL 을 로깅한다. 어댑터 내부에서 못 끔 — **진입점에서 `logging.getLogger("httpx").setLevel(WARNING)` 필요**. 현재 `pilot.py main` 의 `basicConfig(level=INFO)` 에 이 가드가 없고, EODHD 전용 진입점도 없음. EODHD 를 라이브로 돌리는 진입점이 생기면 반드시 가드 동반.

**Why:** logging-rules BLOCKING(민감정보 로깅 금지). 쿼리 토큰은 헤더와 달리 URL 노출 경로가 추가됨.
**How to apply:** EODHD 라이브 실행 진입점(pilot 에 EodhdSource 주입 포함) 추가 PR 을 보면 httpx 로거 레벨 가드가 있는지 확인. 없으면 high.
관련: [[project-stockpick-security]]
