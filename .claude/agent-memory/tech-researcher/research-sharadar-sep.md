---
name: research-sharadar-sep
description: Sharadar SEP(Equity Prices, Nasdaq Data Link) 가격전용 단독 실측 — 폐지종목 우수·1998~·3컬럼 조정체계·but 해지 30일내 삭제의무(재현성 탈락) (2026-06-16).
metadata:
  type: reference
---

2026-06-16 실측. 가격 전용(SF1 재무 제외, EDGAR가 재무 담당) 관점. [[research-us-data-sources]] 보완·정정.

**커버리지(강점)**: 21,000+ active+delisted 티커, EOD 1998~present, survivorship-bias-free 명시. 매 영업일 17:30/23:30 ET 갱신. ACTIONS 테이블에 split/dividend/spinoff/delist reason/ticker change.

**조정 컬럼 체계(정밀 — 기존 메모리 정정)**:
- `close/open/high/low/volume` = split + **stock dividend**만 조정
- `closeadj` = split + stock dividend + **cash dividend** + spinoff 전부 backward-adjust (총수익 기준)
- `closeunadj` = **무조정 raw**(우리 "원주가+adj_factor" 모델에 매핑할 진짜 원주가)
- → raw(closeunadj) + 총수익(closeadj) 둘 다 제공. split-only 분리 컬럼은 없음(close는 stock dividend 포함).

**⛔ 라이선스(재현성 탈락 사유 — SimFin과 동급)**:
- Nasdaq Data Link 약관 §6.3: 종료/만료 시 데이터 delete/purge 의무
- QuantRocket(재판매) Sharadar 약관: "해지 30일 내 모든 시스템에서 Services Data 전체 삭제" + "QuantRocket 서비스 내에서만 사용" + 재배포 금지
- → **구독 해지 후 다운로드 데이터 보유 불가** = 우리 재현성 핵심요건 위반. [[research-simfin]] 와 동일 탈락.

**가격(미확인)**: SEP 단독 월/연 가격은 data.nasdaq.com/databases/SEP/pricing 이 로그인+라이선스선택 게이트 뒤 — 공개값 없음. QuantRocket·Datarade도 비공개/403. 기존 메모리 "SEP ~$39/월·$399/년"은 출처 재확인 실패 → 신뢰 보류. 견적은 로그인 또는 영업 문의 필요.

**기술적합(우수)**: pip install nasdaq-data-link → import nasdaqdatalink. get_table('SHARADAR/SEP', ...) + bulkdownload()(zip) + qopts.export=true. 순수 REST/Python, OS중립 → Linux/Docker OK(Norgate Windows 종속 문제 없음).

**rate limit**: 프리미엄 5,000콜/10분, 720,000콜/일. Table Exporter 10회/시. bulk 30요청/테이블/일(신규 25).

**판정**: 가격데이터 품질·폐지종목은 골드스탠다드급이나 **해지 후 삭제 의무로 재현성 탈락**. 영구 보유 가능한 EODHD/Tiingo/Massive 가 우리 요건엔 우선. 6개월 재검증(약관·가격).
