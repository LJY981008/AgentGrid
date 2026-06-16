---
name: research-eodhd
description: EODHD(EOD Historical Data) 가격전용 관점 실측 — EOD All World $19.99/199년·폐지종목 2000~(11k+,2018기준 깊이차등)·adj both+raw분리·해지후 1개월 삭제의무(재현성 함정)·벌크100콜·공식python (2026-06-16).
metadata:
  type: reference
---

2026-06-16 공식 실측(eodhd.com). 우리 요건 = 가격전용(재무는 EDGAR), Linux/Docker, 1인, 재현성.

**가격 플랜(개인용, 2026)**: Free $0(20콜/일) / **EOD All World $19.99월·$199년($16.58월)** = 가격전용 최저 적합(30년+,split+div) / EOD+Intraday $29.99 / Fundamentals $59.99 / All-In-One $99.99. 우리는 EOD All World면 충분(재무 불필요).

**폐지종목**: US 11,000+ 폐지사 EOD 제공, 2000년 1월 이후 거의 전부. 단 깊이 차등 — 2018년 이후 폐지=Fund+Div/Split+EOD, **2018 이전 폐지=EOD only**. survivorship-bias-free 라고 명시 단정은 안 함(Academy 글로 권고). 티커별 가용성 편차 → support 확인 권고.

**수정주가**: OHLC=raw(무수정), adjusted_close=split+div 둘 다, volume=split만. **raw와 adjusted 분리 제공** → 우리 "원주가+adj_factor" 모델에 적합(원OHLC 보존). 단 adj_factor는 직접 미제공, raw close/adj close 비율로 역산 필요.

**⭐라이선스/해지 약관(재현성 BLOCKING)**: "Upon termination or expiration of the subscription, the subscriber is required to delete all copies of the data in their possession within one (1) month." → **해지 후 1개월 내 전량 삭제 의무. 보유 불가**. SimFin/Sharadar류와 동일 함정. 비전문(개인 투자) 사용은 허용되나 재배포·재판매·접근권 부여 금지(전문은 서면승인 필요).

**벌크**: Bulk API로 거래소 전체 1일치 1요청(US 45k 티커 5~10초). EOD/Splits/Dividends 벌크. CSV/JSON.

**Python/Linux**: 공식 라이브러리 `pip install eodhd`(repo EodHistoricalData/EODHD-APIs-Python-Financial-Library). REST(requests)만으로도 충분 — Windows 데스크톱 종속 없음(Norgate와 대비) → Linux/Docker 적합.

**Rate limit**: 1000요청/분, 100,000콜/일(유료). 콜 소비모델 = EOD 심볼 1요청=1콜, 벌크 거래소=100콜(+심볼 N). Fundamental 10콜, Intraday/Tech/News 5콜. X-RateLimit 헤더.

**품질**: 자체 "정확도 자부하나 오류 불가피, 24/7 지원". 알려진 이슈 = **배당 데이터는 업스트림 제공처발이라 통제 한계**(포럼 dividends-data-accuracy). 배당수정 의존 백테스트 시 주의.

**value_verdict**: 가격전용·폐지·Linux·1인 요건엔 **월 $19.99 최강 가성비**. 단 (1)해지 후 삭제의무 = 재현성 치명 — 구독 유지하거나 원본 raw 스냅샷 합법보관 불가, (2)US 폐지 2000~(30년 풀 아님)·2018이전 폐지 EOD only, (3)배당 정확도 업스트림 의존.

**미확인**: 2018이전 폐지 EOD의 corporate action 보정 완전성, US 상장종목(비폐지) EOD 실제 최장 시작연도(30년+ 주장=~1990s).
