"""stockpick — 개인 투자용 한국 주식 주가 분석.

플로우(stock-1st_plan): 30년 데이터 → 정량 룰로 코스피/코스닥 각 Top20 →
사용자 세션 토의로 Top5 → 분산투자 → 추적·보정.

모듈 경계 (AI 자동화 미래 확장이 막히지 않게):
- data    : 수집·저장·정규화 (FDR/pykrx 벌크 + KRX OpenAPI 일일, Parquet+PG)
- rules   : Top20 정량 랭킹 룰 (백테스트로 검증된 것만 신뢰)
- backtest: 룰 검증 (생존편향·수정주가·룩어헤드 회피)
"""

__version__ = "0.0.1"
