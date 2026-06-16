---
name: impl-tiingo-adapter
description: Tiingo EOD 가격 어댑터(첫 도메인 구현) 설계 패턴 — adj_factor·인증·에러분류·유니버스 한계
metadata:
  type: project
---

`src/stockpick/data/tiingo.py` `TiingoSource` = `DataSource` Protocol 첫 구현체(B-pipeline). 패턴:

- **수정주가 원본 불변**: 응답 raw OHLCV 를 DailyBar 에 그대로, `adj_factor = adjClose / close`
  (Decimal). close<=0 / adjClose 결측 = factor 1 + WARNING(조용한 왜곡 금지). adjusted = raw*factor.
- **인증**: `TIINGO_API_KEY` 를 **호출 시점** os.environ 에서(import 시점 아님 — 테스트 모킹). 헤더
  `Authorization: Token <KEY>`(⚠️ Bearer 아님). 키는 로깅·예외메시지·repr·url 어디에도 비노출.
- **HTTP**: httpx(0.28.1, mypy strict 네이티브·스텁 불요). client 주입 가능 → 테스트는
  `httpx.MockTransport` 로 라이브 0. 에러 분류: 429=TiingoRateLimitError(Retry-After),
  401·403=TiingoAuthError, 기타 4xx·5xx=TiingoResponseError(status_code), 타임아웃 별도. 광역 except 금지.
- **iter_universe = NotImplementedError**: 명세상 전체 종목 나열 수단 부재(utilities/search 는 검색어
  기반·limit/페이지네이션 없음, supported_tickers ZIP 명세에 없음). 빈 리스트로 조용히 누락하면
  생존편향 BLOCKING 위반이라 명시적 실패. 본격 유니버스는 Sharadar SEP(M2). search_assets()=검색 보조.

**Why:** 첫 실데이터 어댑터 — 이후 Parquet 저장·랭킹/백테스트의 입력(`list[DailyBar]`) 원천.
**How to apply:** 다음 가격 소스(Sharadar) 어댑터도 같은 Protocol·같은 원본불변/에러분류/키비노출
패턴 따름. 의존성 추가는 [[env-docker-uv-add]] 절차. 명세 확인은 docs/apis/tiingo/*.json(기억 금지).
검증 정본은 컨테이너 exec(ruff/mypy/pytest). work-history: 2026-06-16-B-pipeline-tiingo-어댑터.
