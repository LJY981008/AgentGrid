---
name: research-us-data-sources
description: 미국주식 유료/저가 생존편향-친화 데이터소스 5종(EODHD/FMP/Sharadar/Norgate/Intrinio) 실측 비교 — PIT재무·폐지종목·corporate action·1인비용 (2026-06-16).
metadata:
  type: reference
---

2026-06-16 실측. 도메인이 한국주식 → **미국주식 주력**으로 전환됨(사용자 지시). BLOCKING 1순위 = 폐지종목 포함 + point-in-time 재무.

**생존편향+PIT 적합 순위 (1인용)**:
1. **Sharadar SEP+SF1** (Nasdaq Data Link) — PIT 골드스탠다드. SF1 datekey=공시일 → 룩어헤드 회피. ARQ/ART = as-reported, restated 구분. 폐지종목 포함(21,000+ 티커, SEP 1998~/SF1 1990~). SEP closeadj=수정주가. 개인 비전문 라이선스 OK, 전문활동 시 별도. SEP ~$39/월(10년)·$399/년(풀). **SF1 월가격은 로그인 게이트 뒤 — 공개 미확인**.
2. **EODHD** — 최저가. EOD All World $19.99/월(폐지종목 포함,30년+), Fundamentals $59.99/월, All-In-One $99.99/월. 폐지종목 = Exchanges API `delisted=1`. **US 폐지 ~2000년부터**(30년 풀 아님). PIT는 자체주장(공시일 이후 추가+restated 구분) — Sharadar만큼 검증 안 됨. 100k콜/일,1000/분.
3. **Norgate Data** — 가격/지수 특화. Platinum $630/년(≈$52.5/월) 폐지종목+1990~(1950 옵션), Gold $360/년(20년,폐지X). **데스크톱 NDU(Windows) 상주 필수** → Linux/compose 환경 부적합. 펀더멘털은 현재값 위주(PIT 재무 약함).
4. **FMP** — Starter$22 Premium$59 Ultimate$149/월. Delisted Companies API 있음, 30년+. **PIT 정확도는 restatement 이슈 알려짐 — 백테스트 신뢰 주의**. Premium 750콜/분.
5. **Intrinio** — 개인용 비쌈. US Fundamentals $9,600/년. **폐지종목 가격 2007~만**(30년 부적합). 탈락.

**미확인(재검증)**: Sharadar SF1 개인 월가격(로그인 필요), EODHD PIT 재무의 실제 공시일 정확도(자체주장), FMP restatement 심각도. 6개월 주기.
