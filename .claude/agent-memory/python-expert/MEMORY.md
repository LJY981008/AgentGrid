# python-expert 메모리

- 도메인: stockpick = 개인 투자용 한국주식. 30년 정량 Top20 → 수동 Top5 → 분산투자 추적·보정
- 스택: Python 3.12+/uv/ruff/mypy(strict)/pytest, src 레이아웃. 계약 = src/stockpick/types.py
- 데이터: 벌크 FDR+pykrx / 일일 KRX OpenAPI / 검증 KIS (docs/research/2026-06-16-한국주식-데이터소스.md)
- 저장: Parquet+DuckDB(백테스트) + PG18(운영). 모듈경계 data→rules→backtest (하위는 상위 import 금지)
- ⚠️ 금융 BLOCKING: 생존편향(폐지종목 포함)·룩어헤드(≤t)·수정주가 통일·백테스트 검증 전 룰 신뢰 금지
- 아직 도메인 구현 0 — 첫 구현 시 python-conventions 초안을 실측 예시로 갱신
