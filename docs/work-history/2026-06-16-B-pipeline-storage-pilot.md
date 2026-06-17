# 2026-06-16 B-pipeline — 저장층(Parquet) + 라이브 파일럿 (S3~S4)

- **유형**: 일반 구현
- **관련 기획/이슈**: M1 §3(Parquet 레이아웃)·§5(BLOCKING)·S3~S4 / [[2026-06-16-B-pipeline-tiingo-어댑터]] (어댑터 `list[DailyBar]` 소비) / [[2026-06-16-B-contract-미국계약]] (DailyBar·Exchange 계약) / api-spec-reference 규칙
- **시작 시점 커밋**: `096e7f3` → **완료 커밋**: `0f69a53`

## 의도/목적 — 왜 이 작업을 하나

Tiingo 어댑터가 뽑은 단일 ticker 의 `list[DailyBar]` 를 **백테스트 1차 진실원본인 Hive 파티션 Parquet**
로 영속화하고, 적재 결과를 DuckDB 로 스캔해 **금융 무결성(중복·adj_factor·OHLC 정합)** 을 게이트로
검증한다. 그 위에 라이브 파일럿(`pilot.py`)으로 분할 표본(AAPL 4:1·NVDA 10:1·TSLA 3:1 등)을 실제
끌어와 **수정주가(adj_factor) 가 분할 비율과 부합하는지 교차검증**한다. 이 게이트가 M1(데이터 신뢰성)의
S3~S4 에 해당하며, PASS 전 M2(백테스트) 착수 금지.

## 계획 (개요)

1. 의존성: `pyarrow`(Parquet 쓰기) + `duckdb`(스캔/검증) `uv add`. pandas 는 저장에 불요 → 추가 안 함(단계별).
2. `src/stockpick/data/storage.py`:
   - `write_daily_bars(bars, *, exchange, base_dir)` → Hive 파티션 `daily_bar/exchange={EX}/year={YYYY}/`.
   - 가격은 pyarrow **decimal128**(float64 다운캐스트 금지 — 정밀 BLOCKING), volume bigint, value nullable.
   - 메타 `source`·`ingested_at` 동반(재현성). 멱등: 같은 (ticker,trade_date) 재적재 시 덮어쓰기 시맨틱.
   - `verify_parquet(base_dir)` DuckDB 검증: (a)중복=0 (b)adj_factor>0 (c)OHLC 정합 (d)리포트. 위반=게이트 실패.
3. `src/stockpick/data/pilot.py` — 파일럿 유니버스(ticker→exchange, 분할 표본 포함) 오케스트레이션 +
   `python -m stockpick.data.pilot` 진입점. 라이브는 컨테이너 exec 로 별도 실행(테스트 아님).
4. `tests/test_storage.py` — 합성 DailyBar(분할 케이스 adj_factor≠1 포함) 모킹, 라이브 0.

## Before — 수행 전 실측

- `src/stockpick/data/` = `__init__.py`, `source.py`(Protocol), `tiingo.py`(어댑터, S1~S3 완료).
- `pyproject.toml` `dependencies = [httpx>=0.28.1]`. 컨테이너 .venv 에 pyarrow/duckdb 없음(실측: ImportError).
- tests = `test_contract.py`(5), `test_tiingo.py`(21) = 26 passed.
- `.gitignore` 에 `data/parquet/`·`*.parquet` 이미 존재(확인만, 추가 불요).
- 컨테이너 `TIINGO_API_KEY` 주입 확인(KEY_SET=yes). 자동 테스트는 모킹이라 키 불요.

## After — 수행 후 실측

- **검증**(컨테이너 정본 `docker compose exec -T app`):
  - `ruff check src tests` → All checks passed!
  - `ruff format --check src tests` → 13 files already formatted
  - `mypy` → Success: no issues found in 13 source files
  - `pytest` → **42 passed** (기존 26 + test_storage 11 + test_pilot 5), 0.37s
- **라이브 파일럿**(별도 실행, `docker compose exec -T app python -m stockpick.data.pilot`, 키 주입):
  - 5종목 전부 PASS, 각 2124행, 2018-01-02~2026-06-15. rate limit 미발생. 총 10620행·5 tickers·중복 0.
  - 멱등 재실행: 10620행·중복 0 불변(확인).
  - ⭐ **분할 수정주가 교차검증**(분할 직전 거래일 adj_factor):

    | ticker | 분할 | prev_date | adj_factor(실측) | 기대(1/N) | 부합 |
    |---|---|---|---|---|---|
    | AAPL | 4:1 | 2020-08-28 | 0.2425154805 | 0.25 | O (배당 누적조정으로 약간 낮음) |
    | NVDA | 10:1 | 2024-06-06 | 0.0998302068 | 0.10 | O |
    | TSLA | 3:1 | 2022-08-24 | 0.3333333333 | 0.3333 | O |

  - Decimal 보존 실측(DuckDB): NVDA close=`1209.9800000000`(Decimal), adj_factor scale=37(Decimal) — float 다운캐스트 없음.
- **변경 규모**: 신규 `storage.py`(332) · `pilot.py`(229) · `test_storage.py`(193) · `test_pilot.py`(118).
  `pyproject.toml`(+pyarrow,+duckdb) · `uv.lock`(+80줄). data/parquet 산출물은 gitignore(미커밋).
- **커밋**: `0f69a53` (feat: B-storage + 라이브 파일럿)

## 비교/회고

- **의도 대비 달성도**: 저장층+파일럿+모킹 테스트 완료, 검증 전부 통과, 라이브 5종목 PASS, 분할
  교차검증 3종 부합. M1 S3~S4 게이트 달성.
- **⚠️ 라이브에서 발견한 2건(설계가 잡아낸 것 + 직접 잡은 것)**:
  1. **adj_factor scale 초과(게이트가 발견)**: NVDA 10:1(factor≈0.0247)에서 나눗셈 scale=29 가
     초기 가정 28 을 초과 → `PrecisionError`(조용한 반올림 거부, 설계대로 동작). scale 37(precision
     38)로 상향. factor 의 28자리 꼬리는 나눗셈 인공물(의미정밀도 아님) → 근본 정합은 어댑터
     `_compute_adj_factor` 정밀도 통제(후속, storage.py NOTE 주석).
  2. **멱등 덮어쓰기 입도 버그(라이브 회귀로 발견)**: 초기 구현은 (exchange, year) **파티션 단위**로
     기존 파일 전체를 purge 후 단일 `data.parquet` 재작성 → 파일럿이 ticker별로 적재하니 같은
     NASDAQ·연도를 공유하는 이전 ticker(AAPL/NVDA/TSLA)가 **조용히 소실**되고 MSFT만 남았다
     (검증 게이트는 "현재 트리"만 보니 PASS — 소실을 못 잡음). → 파일을 **ticker별 분리**
     (`year={YYYY}/{ticker}.parquet`)로 수정, 같은 ticker 파일만 덮어쓰기. 회귀 봉인 테스트
     `test_same_partition_different_tickers_preserved` 추가. 재실행 후 5 tickers/10620행 정상.
- **금융 BLOCKING 준수**: Decimal128 정밀(float 금지)·원본 불변·source/ingested_at 재현성·멱등(중복 0)·
  검증 게이트(adj_factor>0·OHLC 정합). 생존편향: 파일럿은 현재상장 위주(폐지 미포함) 한계 명시 —
  Sharadar SEP(M2) 보강 대상.
- **후속 작업**:
  - [ ] 어댑터 `_compute_adj_factor` 정밀도 통제(나눗셈 무한소수 꼬리 → 의도 정밀도 quantize). M2 전.
  - [ ] **검증 게이트 보강**: 현재 verify 는 "현재 트리"만 봐서 데이터 소실을 못 잡았다 — 기대 종목·
        행수 대비 누락 탐지(예: 적재 전후 ticker 집합 비교)를 게이트에 추가 검토.
  - [ ] 생존편향: 폐지종목 유니버스(Sharadar SEP) — 파일럿 한계.
  - [ ] DuckDB 검증의 ASOF·ticker_history 연계는 백테스트 단계(M2).
