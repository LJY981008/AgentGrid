# python-expert 메모리

- 도메인: stockpick = 개인 투자용 **미국**주식(2026-06-16 한국→미국 전환, ADR-002). 30년 정량 Top20 → 수동 Top5 → 분산투자 추적·보정
- 스택: Python 3.12+/uv/ruff/mypy(strict)/pytest, src 레이아웃. Docker 정본(compose app 컨테이너). 계약 = src/stockpick/types.py
- 식별자: **CIK**(안정·영구) = 조인 기준 / **ticker**(시변·재사용) = 가격 조회 키. DailyBar 는 ticker+trade_date 키
- 데이터: 가격 = **Tiingo**(파일럿) → Sharadar SEP(M2). API 명세 진실원천 = docs/apis/tiingo/*.json (기억 금지)
- 저장: Parquet+DuckDB(백테스트) + PG18(운영). 모듈경계 data→rules→backtest (하위는 상위 import 금지)
- ⚠️ 금융 BLOCKING: 생존편향(폐지종목 포함)·룩어헤드(≤t)·수정주가 통일·백테스트 검증 전 룰 신뢰 금지
- [Tiingo 어댑터 구현 패턴](impl-tiingo-adapter.md) — 첫 도메인 구현. adj_factor·인증·에러분류·유니버스 한계
- [Parquet 저장층 함정](impl-parquet-storage.md) — 라이브 실측 2건: adj_factor scale 초과·멱등 입도(ticker별 파일). pyarrow strict 우회
- [컨테이너 uv add 권한 함정](env-docker-uv-add.md) — exec uv add 권한거부, run --user 1000 우회 절차
