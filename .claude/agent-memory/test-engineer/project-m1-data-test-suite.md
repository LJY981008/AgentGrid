---
name: project-m1-data-test-suite
description: M1 미국 데이터 파이프라인(types/source/tiingo/eodhd/storage/pilot/_adjust) pytest 현황과 알려진 커버리지 공백
metadata:
  type: project
---

M1 데이터 파이프라인(미국, ADR-002) 테스트는 컨테이너 `stockpick-app` 안에서만 실행 가능하다 — 호스트엔 pyarrow/duckdb/httpx 미설치, uv/.venv 없음.

실행: `docker compose exec -T app sh -c 'PYTHONPATH=src python -m pytest -q'` (호스트 `python` 없음, `python3`만).

**Why:** 사용자 환경엔 의존성이 컨테이너에만 있다. 라이브 의존 금지 규칙대로 모든 테스트는 httpx.MockTransport·합성 DailyBar·tmp_path 로 라이브 0.

**How to apply:** 이 모듈군 테스트를 돌릴 땐 컨테이너 exec 로. 2026-06-16 실측 77 통과(contract 5/eodhd 26/pilot 6/storage 19/tiingo 21), ruff 통과.

알려진 커버리지 공백(리뷰 시 재확인):
- `_adjust.compute_adj_factor` 직접 단위테스트 없음(어댑터 경유만) — raw<0·12자리 quantize 반올림 경계 미핀.
- 음수/0 가격(센티넬 -1 등)을 어떤 게이트도 안 잡음 — OHLC 게이트는 순서만 검사. verify_parquet 통과함(실측).
- EodhdSource.iter_universe 부분실패(active 성공·delisted 429) 미검 — 전파됨(survivorship loud-fail) 확인됨.
- 교차거래소 동일 (ticker,date) 중복은 glob 전파로 잡힘(실측) — 미검.
