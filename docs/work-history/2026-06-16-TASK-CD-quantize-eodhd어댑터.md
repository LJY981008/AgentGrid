# 2026-06-16 TASK-C/D — adj_factor 정밀도 통제(공유 헬퍼) + EodhdSource 어댑터

- **유형**: 일반 구현
- **관련 기획/이슈**: M1 §5(정밀도 BLOCKING)·생존편향 / [[2026-06-16-B-pipeline-storage-pilot]](scale 37 밴드에이드 후속) / [[2026-06-16-B-pipeline-tiingo-어댑터]](공유 헬퍼로 리팩터) / api-spec-reference 규칙(docs/apis/eodhd)
- **시작 시점 커밋**: `734a52f` → **완료 커밋**: `<커밋 시 기입>`

## 의도/목적 — 왜 이 작업을 하나

**TASK-C**: B-pipeline 파일럿에서 `_compute_adj_factor` 의 adjClose/close 나눗셈이 무의미한 무한소수
꼬리(scale 28~29)를 만들어 저장층 decimal128 컬럼 scale 을 37 로 임시 상향했던 밴드에이드를 근본
해소한다. 산출 단계에서 **의도 정밀도(소수 12자리)로 quantize** 하고, 이 산출 로직을 **공유 헬퍼**로
추출해 Tiingo·EODHD 양 어댑터가 재사용한다(중복 제거 + 정밀도 일관).

**TASK-D**: 가격 소스 다변화(생존편향 보강·소스 교체 자유)를 위해 `DataSource` Protocol 의 두 번째
구현 `EodhdSource` 를 추가한다. EODHD 는 Tiingo 와 달리 폐지종목 유니버스 나열이 가능하므로
`iter_universe` 를 실제 구현(활성+폐지 병합) — 생존편향 회피의 핵심. 라이브 호출 0(결제 후 별도 파일럿).

## 계획 (개요)

1. `src/stockpick/data/_adjust.py` — `compute_adj_factor(adjusted, raw, *, source, ticker, trade_date)`.
   quantize 12자리(ROUND_HALF_EVEN), 경계(adjusted 결측·raw<=0 → 1 + WARNING).
2. `tiingo.py` 리팩터(로컬 `_compute_adj_factor` 제거 → 헬퍼 사용). `storage.py` `_FACTOR_SCALE` 37→12.
3. `eodhd.py` — 명세 준거 어댑터(쿼리 토큰 인증·심볼 `.US`·adj_factor 헬퍼·iter_universe 병합·에러 분류).
4. `tests/test_eodhd.py` — httpx MockTransport, 라이브 0. 기존 test_tiingo/test_storage 회귀 갱신.

## Before — 수행 전 실측

- `data/` = `__init__.py`·source.py·tiingo.py·storage.py·pilot.py (EODHD·_adjust 없음).
- `tiingo.py` 에 로컬 `_compute_adj_factor`(adjClose/close, quantize 없음). `storage.py` `_FACTOR_SCALE=37`.
- 테스트 baseline: `77 passed`(test_contract·test_tiingo 21·test_storage 19·test_pilot·없던 test_eodhd).
- 디스크에 *.parquet 없음(stale 데이터 없음 — 재적재 영향 없음).
- 명세 실측: `docs/apis/eodhd/end-of-day-historical-data.json`(base `https://eodhd.com/api`,
  `GET /eod/{SYMBOL}`, response_fields date/open/high/low/close/adjusted_close/volume, 거래대금 필드
  없음), `exchanges-api-...json`(`/exchange-symbol-list/{EX}`, `delisted=1`=폐지만, 활성+폐지 동시
  파라미터 없음), `delisted-stock-companies-data.json`(폐지 목록은 exchange-symbol-list?delisted=1 경유).

## After — 수행 후 실측

- **검증**(컨테이너 정본 `docker compose exec -T app sh -c '...'`):
  - `ruff check src tests` → All checks passed!
  - `ruff format --check src tests` → 16 files already formatted
  - `mypy` → Success: no issues found in 16 source files
  - `pytest` → **77 passed**, 0.49s (test_eodhd **26** 신규 + test_tiingo 21 + test_storage 19 + 나머지)
- **TASK-C 정밀도 결정·근거**: adj_factor quantize = **소수 12자리**(ROUND_HALF_EVEN).
  - 근거: adj_factor 는 가격(유효숫자 ~6자리)에 곱하는 비율. 12자리면 factor 가 1e-3 수준(대규모 분할
    누적)이어도 유효숫자 9자리 이상 → 가격 정밀도를 충분히 상회(반올림 오차 ≪ 가격 정밀도). 분할 비율
    (0.25, 0.1, 0.333…)·배당 누적조정 충분 표현. 나눗셈 28자리 꼬리는 인공물(adjClose 가 소수 2~4자리).
  - 저장층 `_FACTOR_SCALE` 37 → **12** 축소(헬퍼 `ADJ_FACTOR_DECIMAL_PLACES` 와 동일해야 손실 없이
    적재). 정수부 26자리 여유(precision 38)로 역분할도 수용. 실측 quantize(컨테이너 Decimal):
    AAPL 127.46/129.04=`0.987755734656`(scale 12), NVDA 120.9398/1209.98=`0.099951900031`,
    동일가=`1.000000000000`, 역분할 300/100=`3.000000000000`.
- **TASK-D 명세 준거 확인**(어느 엔드포인트·필드):
  - 가격: `GET {base}/eod/{TICKER}.{EX}` (base=`https://eodhd.com/api`), params `from`/`to`/
    `period=d`/`order=a`/`fmt=json`. raw open/high/low/close + `adjusted_close` + volume → DailyBar.
    `value=None`(EODHD EOD 응답에 거래대금 필드 없음 — 명세 response_fields 에 부재).
  - 인증: `?api_token=<KEY>` 쿼리(헤더 아님). 키 = `EODHD_API_KEY`.
  - 유니버스: `GET {base}/exchange-symbol-list/US` (활성) + `?delisted=1`(폐지만) **두 호출 병합**
    (동시 반환 파라미터 명세에 없음). 응답 Code/Name/Exchange 사용. cik 미제공 → "".
- **변경 규모**: 신규 `_adjust.py`(88)·`eodhd.py`(469)·`test_eodhd.py`(354). 수정 `tiingo.py`
  (-39 라인 로컬함수 제거·헬퍼 사용)·`storage.py`(scale 37→12·주석)·`test_tiingo.py`·`test_storage.py`.
- **커밋**: `<SHA>` (커밋은 사용자 요청 시 — 메인 보고 후)

## 비교/회고

- **의도 대비 달성도**: TASK-C 공유 헬퍼 추출 + scale 근본 해소(37→12), TASK-D 어댑터+iter_universe
  실구현(폐지 병합)+모킹 26 테스트, 검증 전부 통과. 라이브 0 준수.
- **금융 BLOCKING 준수**:
  - 정밀도: float 금지·Decimal·quantize 12자리(저장 scale 정합)·scale 초과 PrecisionError(adj_factor
    13자리 회귀 테스트 추가).
  - 수정주가 통일: 두 소스 모두 공유 헬퍼(adjusted/raw) — 계약 불변식 adjusted=raw*adj_factor 유지.
    ⚠️ EODHD 명세 caveat "(raw close/adjusted_close) 역산"은 역수 표현 — 우리 계약은 adjusted/raw 가
    맞음(_adjust docstring 에 명시). 분자/분모 혼동이 수익률 부호/배율을 뒤집을 수 있어 BLOCKING 주의.
  - 생존편향: EODHD iter_universe 가 활성+폐지(delisted=1) 병합 — 폐지 포함이 기본. cik 미제공 한계
    명시(빈 문자열, EDGAR 매핑 후속).
- **⚠️ 미해결·다음 권고**:
  - [ ] **토큰 URL 로깅 누출(BLOCKING, 진입점)**: httpx 라이브러리 INFO 로거(`httpx._client`)가 토큰이
        실린 완성 URL 을 로깅한다(어댑터 내부에서 못 끔). 운영/파일럿 진입점에서
        `logging.getLogger("httpx").setLevel(WARNING)` 가드 필수. test_eodhd 가 이 사실을 드러냄
        (우리 모듈 로거만 검사하도록 스코프). 진입점 추가 전 라이브 실행 금지.
  - [ ] **cik 미제공**: EODHD exchange-symbol-list 에 CIK 없음 → Stock.cik="". cik 가 조인 기준이라
        백테스트 착수 전 EDGAR ticker→CIK 매핑 보강 필수(id-mapping 또는 EDGAR).
  - [ ] **exchange 매핑 한계**: US 통합 코드는 세부 거래소(NYSE/NASDAQ) 분리 불가 → OTC 보수 분류
        (종목은 보존). 정확 거래소는 개별 fundamentals 로 보강.
  - [ ] **폐지일 미제공**: delisted=1 응답에 delisted_at 없음 → None(출처는 로그 구분). 정확 폐지일은
        개별 EOD 마지막 거래일 등으로 후속 보강.
  - [ ] **라이브 파일럿**: EODHD 결제 후 별도(Free 20콜/일·과거 1년 한계). 분할 교차검증 재수행 권고.
  - [ ] 명세 caveat: JSON 필드명 casing 은 demo 호출(fmt=json) 실측으로 최종 확정 권고(현재 소문자
        표기는 명세의 추정 보강분).
