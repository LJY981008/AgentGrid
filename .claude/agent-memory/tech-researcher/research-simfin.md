---
name: research-simfin
description: SimFin 미국주식 무료 재무층 실측 — 폐지종목 포함(생존편향 대응O), but PIT는 표준셋이 최신 restatement 덮어씀(룩어헤드 위험), 무료5년+API v3, simfin SDK 사실상 미유지 (2026-06-16).
metadata:
  type: reference
---

2026-06-16 실측. stockpick 백테스트 무료 재무층 후보로 SimFin 정밀 검증. 메인리드 우려 4개 판정.

**판정 요약 (covers_my_downsides)**:
1. 생존편향 → **충족**: 폐지종목 과거 재무 포함, survivorship-bias-free 광고. (단 폐지종목 *수*·시작연도는 공개 미명시)
2. PIT(룩어헤드) → **부분/미충족(핵심 함정)**: PUBLISH_DATE/RESTATED_DATE 컬럼은 있으나, **표준 데이터셋은 최신 restatement 값으로 덮어씀 → SimFin 공식이 "not point-in-time"이라 명시**. PUBLISH_DATE로 공시일 이후 필터링은 가능하나 *값 자체는 정정 후 최신* → 정정공시 회사는 룩어헤드 잔존. as-reported 원본 보존 안 됨. simfin SDK엔 PIT 파라미터 없음(annual/quarterly/ttm 변형만).
3. 커버리지 → **충족(필드)/부분(기간)**: US ~5,000종목. 재무 history 2003~(2024말 25년 목표였음, 30년 미달). 거래소 NYSE/NASDAQ 구분 명문 미확인. 필드: 손익+재무상태표+현금흐름표 표준화 → 우리 superset(매출·순이익·EPS·자기자본·총자산·영업이익·발행주식수) 충족.
4. 무료약관 → **부분**: 무료=5년 history·500크레딧/월·2 calls/s·bulk(CSV/ZIP)+API 포함. "12개월 지연" 주장은 *과거 약관* — 현재 가격페이지는 5년 history로 표기(지연 명문 사라짐, 재확인 필요). 유료 START$15/BASIC$35(15년)/PRO$71(20년+). 라이선스: 구독 유효기간만 사용, 해지 시 삭제 의무, 재배포 금지(개인용 OK).

**품질 이슈(실측)**: ML+전문가 QA 광고하나 GitHub 이슈 실제 보고 — 티커 변경으로 가격 깨짐(ACRX→TLPH), 재무상태표 수학적 불일치, 발행주식수 자릿수 오류(62,551 vs 62,551,281). 정량 백테스트 전 sanity check 필수.

**simfin Python SDK**: 마지막 릴리스 0.9.2 (2023-06-13), 18개월+ 정체, 오픈이슈 10. MIT. **사실상 미유지** → API v3 직접 호출 또는 자체 로더 권장.

**결론**: 생존편향은 잘 잡지만 **PIT 미흡이 백테스트 BLOCKING과 충돌**. 정정공시 비율 높은 종목에서 룩어헤드 = 수익 부풀림. 무료 재무 "탐색/프로토타입"엔 적합, 본격 30년 백테스트는 Sharadar SF1(datekey=공시일 PIT) 우위. [[research-us-data-sources]] [[research-us-free-data-sources]].

**미확인(재검증)**: 현재 무료티어 12개월 지연 실제 적용 여부(가격페이지 vs 과거 문서 충돌), 폐지종목 정확한 수·시작연도, API v3에 별도 PIT/banked 엔드포인트 존재 여부. 6개월 주기.
