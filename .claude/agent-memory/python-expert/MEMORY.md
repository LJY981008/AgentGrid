# python-expert 메모리

- 도메인: stockpick = 개인 투자용 **미국**주식(2026-06-16 한국→미국 전환, ADR-002). 30년 정량 Top20 → 수동 Top5 → 분산투자 추적·보정
- 스택: Python 3.12+/uv/ruff/mypy(strict)/pytest, src 레이아웃. Docker 정본(compose app 컨테이너). 계약 = src/stockpick/types.py
- 식별자: **CIK**(안정·영구) = 조인 기준 / **ticker**(시변·재사용) = 가격 조회 키. DailyBar 는 ticker+trade_date 키
- 데이터: 가격 = **Tiingo**·**EODHD**(파일럿) → Sharadar SEP(M2). API 명세 진실원천 = docs/apis/{tiingo,eodhd}/*.json (기억 금지)
- 저장: Parquet+DuckDB(백테스트) + PG18(운영). 모듈경계 data→rules→backtest (하위는 상위 import 금지)
- ⚠️ 금융 BLOCKING: 생존편향(폐지종목 포함)·룩어헤드(≤t)·수정주가 통일·백테스트 검증 전 룰 신뢰 금지
- [Tiingo 어댑터 구현 패턴](impl-tiingo-adapter.md) — 첫 도메인 구현. adj_factor·인증·에러분류·유니버스 한계
- [Parquet 저장층 함정](impl-parquet-storage.md) — 라이브 실측 2건: adj_factor scale 초과·멱등 입도(ticker별 파일). pyarrow strict 우회
- [컨테이너 uv add 권한 함정](env-docker-uv-add.md) — exec uv add 권한거부, run --user 1000 우회 절차
- [EODHD 어댑터 구현](impl-eodhd-adapter.md) — 쿼리 토큰 인증·httpx URL 토큰 누출(진입점 가드)·폐지 유니버스 병합·cik 미제공 한계
- [adj_factor 방향·정밀도 함정](gotcha-adj-factor-direction.md) — 공유 헬퍼 adjusted/raw quantize 12자리. EODHD 명세 caveat 역수 함정(돈 걸림)
- [rules 모듈 첫 구현(모멘텀)](impl-rules-momentum.md) — 룩어헤드 2중 가드·스캔/계산 분리·sabotage 검증·데이터셋 컨테이너 전용·ruff E501 한글 함정
- [FastAPI API 층(M3)](impl-fastapi-api.md) — DI 테스트·키비노출·path-traversal·계약 wire-shape(거래소별 rank·validated=false)·fastapi 0.137/mypy/B008 함정
- [EODHD garbage 수익률 폭발(S6-b G-3)](gotcha-eodhd-garbage-explosion.md) — e80 근원=tiny분모×sentinel분자·데이터drop 불충분·legit천장 GME 16.2x·캡 K=[-0.95,+19.0]
