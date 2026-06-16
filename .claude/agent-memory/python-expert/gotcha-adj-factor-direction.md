---
name: gotcha-adj-factor-direction
description: adj_factor 산출 방향·정밀도 — 공유 헬퍼 _adjust.compute_adj_factor(adjusted/raw, quantize 12자리). EODHD 명세 caveat 역수 함정
metadata:
  type: project
---

adj_factor 산출은 `src/stockpick/data/_adjust.py` 공유 헬퍼 하나로 통일(Tiingo·EODHD 재사용).
`compute_adj_factor(adjusted, raw, *, source, ticker, trade_date)`.

**규칙**: `adj_factor = quantize(adjusted / raw, 소수 12자리, ROUND_HALF_EVEN)`. 경계(adjusted
결측·raw<=0) → `Decimal("1")` + WARNING.

**Why (방향 — BLOCKING 함정)**: 계약 불변식은 `DailyBar.adjusted = raw * adj_factor`(types.py).
따라서 분자=adjusted(수정종가), 분모=raw(원시종가) 가 맞다. ⚠️ **EODHD 명세 caveat 은 "(raw close /
adjusted_close)로 역산"이라 적지만 그건 역수 표현** — 그대로 쓰면 분자/분모가 뒤집혀 수익률 배율이
틀어진다(돈 걸림). Tiingo(adjClose/close)와 동일식이 맞다.

**Why (정밀도 12자리)**: adjusted/raw 나눗셈은 무의미한 무한소수 꼬리(scale 28~29)를 만든다(소스
adjusted 는 소수 2~4자리뿐 — 꼬리는 나눗셈 인공물). 산출 단계에서 12자리 quantize 로 고정. 가격
유효숫자 ~6자리에 곱하는 비율이라 12자리면 충분(반올림 오차 ≪ 가격 정밀도).

**How to apply**: 새 가격 소스 추가 시 이 헬퍼 재사용(직접 나눗셈 금지). 저장층
`storage.py _FACTOR_SCALE` 은 헬퍼 `ADJ_FACTOR_DECIMAL_PLACES`(=12)와 **반드시 동일**(과거 37
밴드에이드는 TASK-C 에서 해소). scale 초과 값이 새면 PrecisionError(조용한 반올림 금지).

연관: [[impl-parquet-storage]] · [[impl-eodhd-adapter]] · [[impl-tiingo-adapter]]
