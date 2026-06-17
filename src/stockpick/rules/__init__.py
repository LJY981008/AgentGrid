"""rules 모듈 — Top 정량 랭킹(M2 수직 슬라이스).

구성: `_scan`(Parquet→수정주가 시계열, DuckDB·룩어헤드 1차 가드) · `factors`(모멘텀 등 순수 팩터,
룩어헤드 2차 가드) · `ranking`(점수→TopEntry) · `demo`(`python -m stockpick.rules` 진입점).

모듈 경계(python-conventions): `rules` 는 `data`·`..types` 만 의존하고 `backtest`/상위(api·webapp)를
import 하지 않는다. ⚠️ 산출 랭킹은 백테스트(M2 §4.4) 검증 전이므로 알파로 신뢰하지 않는다(§4.1).
"""
