"""backtest 모듈 — 룰 검증(생존편향·룩어헤드·과적합 가드). M2.

rules(랭킹) 위층: rolling as_of 리밸런싱으로 룰을 시간축으로 굴려 자산곡선·지표를 산출한다.
저장소 읽기는 ports(Protocol·DI)로 추상화 — 무료 1년치 골격과 결제후 다년 전체유니버스가
같은 코드로 동작(데이터량 무관). 돈=Decimal, 통계(Sharpe·CAGR)=float 경계 격리.

⚠️ 산출 지표는 데이터 신뢰성(S6) 게이트 통과 전까지 알파 아님(BacktestResult.data_caveats 명시).
"""
