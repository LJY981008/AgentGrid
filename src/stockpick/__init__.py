"""stockpick — 개인 투자용 미국 주식(NYSE/NASDAQ/AMEX) 주가 분석.

플로우(stock-1st_plan): 과거 데이터 → 정량 룰로 Top20 →
사용자 세션 토의로 Top5 → 분산투자 → 추적·보정. (2026-06-16 한국→미국 전환, ADR-002)

모듈 경계 (AI 자동화 미래 확장이 막히지 않게):
- data    : 수집·저장·정규화 (Tiingo 파일럿→EODHD 벌크 + SEC EDGAR 재무(PIT), Parquet+PG)
- rules   : Top20 정량 랭킹 룰 (백테스트로 검증된 것만 신뢰)
- backtest: 룰 검증 (생존편향·수정주가·룩어헤드 회피) — ⚠️ 미구현 스텁(M2 예정)
"""

__version__ = "0.0.1"
