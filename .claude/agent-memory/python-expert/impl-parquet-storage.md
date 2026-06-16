---
name: impl-parquet-storage
description: 일봉 Parquet 저장층(storage.py)의 라이브 실측 함정 2건 — adj_factor scale·멱등 입도
metadata:
  type: project
---

`src/stockpick/data/storage.py` (B-pipeline S3~S4, 2026-06-16). `list[DailyBar]` → Hive 파티션
Parquet(`daily_bar/exchange={EX}/year={YYYY}/{ticker}.parquet`, decimal128, zstd) + DuckDB 검증
게이트. pyarrow 24.0.0 + duckdb 1.5.3.

**라이브 Tiingo 파일럿에서만 드러난 함정 2건(모킹/코드리뷰로는 안 보였음):**

1. **adj_factor decimal128 scale**: factor = adjClose/close 는 기본 Decimal(prec=28) 나눗셈.
   factor<1(분할)이면 유효숫자 28자리가 선행 0 뒤에 와 **scale 이 28 초과**(NVDA 10:1 → 0.0247,
   scale 29 실측). 초기 scale 28 가정이 PrecisionError 게이트에 걸려 발견(설계대로 조용히 반올림
   안 함). → scale 37(precision 38)로 상향. **factor 의 긴 꼬리는 나눗셈 인공물(의미정밀도 아님)** —
   근본 정합은 어댑터 `_compute_adj_factor` 가 의도 정밀도로 quantize 하는 것(후속, M2 전).

2. **멱등 덮어쓰기 입도 = ticker별 파일이어야 함**: 파일을 (exchange, year) **파티션 단위** 단일
   파일로 쓰고 적재마다 파티션을 purge 하면, ticker별로 적재할 때 같은 거래소·연도를 공유하는
   **이전 ticker 가 조용히 소실**된다(라이브: AAPL/NVDA/TSLA 사라지고 MSFT만 남음). 검증 게이트가
   "현재 트리"만 봐서 PASS 로 통과 → 소실 못 잡음. **파일을 `{ticker}.parquet` 로 분리**해 같은
   ticker 파일만 덮어쓰면 해소. 회귀 테스트 `test_same_partition_different_tickers_preserved`.
   ⚠️ 교훈: verify 게이트가 데이터 *소실*을 못 잡는다 — 기대 종목/행수 대비 누락 탐지 보강 필요(후속).

**mypy strict + pyarrow 함정**: `pyarrow.compute.year`·`pyarrow.dataset.write_dataset`·
`ParquetFileFormat` 은 py.typed(partial)에서 미export/untyped → strict 에서 막힘. 우회: 연도 계산은
Python(`bar.trade_date.year`), 쓰기는 `pq.write_table(...)  # type: ignore[no-untyped-call]`.
duckdb 파라미터 바인딩은 `$glob` named(SQL 골격은 리터럴 상수 → `# noqa: S608` 정당).

관련 [[impl-tiingo-adapter]] · [[env-docker-uv-add]].
