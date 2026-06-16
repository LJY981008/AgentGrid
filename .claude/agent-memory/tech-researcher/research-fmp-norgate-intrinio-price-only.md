---
name: research-fmp-norgate-intrinio-price-only
description: 가격전용 저가 survivorship-free EOD 대안 3종 실측 — FMP(채택후보)·Norgate(Linux불가 탈락)·Intrinio($3,100/yr 탈락). raw+adj 분리·약관·Linux적합 (2026-06-16).
metadata:
  type: reference
---

2026-06-16 실측. 재무는 EDGAR가 담당 → 가격 전용 관점. 우리요건: 가격전용·폐지(survivorship-free)·EOD·Linux/Docker·재현성(해지후 보유)·1인.

**결론 순위 (가격 전용)**:
1. **FMP** — 가성비 1위. Premium $59/월(~30년·750콜/분·50GB/월), Starter $22/월(US만), Ultimate $149/월(1분봉·bulk·3000콜/분). **flat $19/월 unlimited real-time(REST+WS)** 별도존재. 폐지종목: "Survivorship Bias Free EOD"(레거시 v4) + "Delisted Companies API"(무료) 존재. ⭐**unadjusted 엔드포인트 별도 제공**(historical-price-eod-non-split-adjusted) → 우리 raw+adj_factor 모델에 최적합(Polygon은 split-adj만이라 footgun). adj 의미: `close`=split만, `adjClose`=split+div. 1990~예시. ⚠️재배포금지·개인↔상업 라이선스 구분(앱으로 과금하면 non-commercial 위반). 해지후 보유 약관 = FAQ 미명시(견적/AE팀 안내) → 재현성 보장 불확실, 별도 확인 필요. PIT 재무 restatement 이슈 알려짐(but 재무는 EDGAR라 무관).
2. **Norgate** — ⛔Linux 불가로 탈락. Platinum $630/yr(폐지O·1990~)·Diamond $787.50/yr(폐지O·1950~ = 30년+ 유일 충족). survivorship-free·index constituent history 우수. **그러나 norgatedata PyPI 패키지가 "NDU(Windows 전용 앱)가 running 상태여야 동작" 명시 + OS classifier Windows only + 로컬 .norgatedata DB 읽음.** compose/Linux 스택과 근본 충돌. 데스크톱 1인 백테스터용으론 최고지만 우리 아키텍처 부적합.
3. **Intrinio** — ⛔비용 탈락. EOD Historical Stock Prices $3,100/yr(~$258/월). 폐지가격 2007~만(30년 부적합). 1인 가격전용엔 과함.

**미확인(재검증)**: FMP 해지후 데이터 보유 약관(공개 미명시·BLOCKING 재현성), FMP Survivorship-free EOD의 폐지가격 history 실제 깊이, FMP Premium 연간가격(월$59확인·연환산 미확정). 6개월 주기. [[research-us-data-sources]] [[research-polygon-massive]] 보완.
