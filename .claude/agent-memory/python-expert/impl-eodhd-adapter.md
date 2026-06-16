---
name: impl-eodhd-adapter
description: EodhdSource 어댑터 구현 핵심 — 쿼리 토큰 인증·httpx URL 토큰 누출·adj_factor 방향·폐지 유니버스 병합·미제공 필드 한계
metadata:
  type: project
---

`src/stockpick/data/eodhd.py` = `DataSource` 두 번째 구현(Tiingo 다음). 라이브 0(모킹까지만).

**Why**: 가격 소스 다변화 + 생존편향 보강. EODHD 는 Tiingo 와 달리 폐지 유니버스 나열 가능.

**How to apply** (EODHD 작업 시):
- 명세 진실원천: `docs/apis/eodhd/*.json`. base=`https://eodhd.com/api`, 가격=`GET /eod/{TICKER}.{EX}`
  (params from/to/period=d/order=a/fmt=json). 응답 필드 소문자 date/open/high/low/close/adjusted_close/
  volume. **거래대금(value) 필드 없음 → value=None**.
- **인증은 `?api_token=<KEY>` 쿼리**(Tiingo 의 Authorization 헤더와 다름). 키 = `EODHD_API_KEY`.
- ⚠️ **httpx 토큰 URL 누출(BLOCKING, 진입점 가드 필요)**: 토큰이 쿼리에 실리므로 httpx 라이브러리
  INFO 로거(`httpx._client`)가 완성 URL(토큰 포함)을 로깅한다. 어댑터 내부에서 못 끔 → 운영/파일럿
  진입점에서 `logging.getLogger("httpx").setLevel(WARNING)` 필수. 라이브 실행 전 미해결.
- `iter_universe(include_delisted=True)`: `/exchange-symbol-list/US`(활성) + `?delisted=1`(폐지만)
  **두 호출 병합**(동시 반환 파라미터 명세에 없음). 폐지 포함이 기본(생존편향).
- **미제공 필드 한계**(조용한 추측 금지·명시): cik 없음→`""`(EDGAR 매핑 후속, cik 가 조인 기준이라
  백테스트 전 필수 해소) / delisted_at 없음→None(출처는 로그 구분) / US 통합 거래소코드는 세부
  거래소 분리 불가→OTC 보수 분류(종목은 보존).
- 에러 분류 = Tiingo 와 동형(Auth/RateLimit/Response, 429·401/403·4xx/5xx). source 라벨 "eodhd".

연관: [[gotcha-adj-factor-direction]] · [[impl-tiingo-adapter]] · [[impl-parquet-storage]]
