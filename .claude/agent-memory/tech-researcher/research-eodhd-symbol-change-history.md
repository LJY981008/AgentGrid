---
name: research-eodhd-symbol-change-history
description: EODHD Symbol Change History API(미국 티커 변경 이력) 엔드포인트 실측 — 폐지/리네임 추적, 생존편향 보정용
metadata:
  type: reference
---

EODHD `GET https://eodhd.com/api/symbol-change-history` — 미국 주식 티커 변경(rename) 이력. 2026-06-16 r.jina.ai 경유 실측(SPA라 직접 WebFetch 빈본문).

- 쿼리: api_token(필수), from(YYYY-MM-DD, 기본 현재-12개월), to(기본 현재), fmt(json/csv, 기본 csv)
- 응답 필드: exchange / old_symbol / new_symbol / company_name / effective(YYYY-MM-DD)
- 소비: "Each request consumes 5 API calls per ticker"
- 플랜: All-In-One, EOD+Intraday — All World Extended
- 커버리지: 2022-07-22~, daily 갱신, "Only US exchanges are supported for the moment"
- **stockpick 관점**: 한국주식(KRX) 미지원이라 직접 사용 불가. 다만 생존편향/티커 변경 추적 패턴 참고용. 메인 EODHD 평가는 [[research-eodhd]] 참조
