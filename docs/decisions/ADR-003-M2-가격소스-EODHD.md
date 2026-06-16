# ADR-003: M2 본격 가격 소스 = EODHD

- **날짜**: 2026-06-16
- **상태**: 승인 ([[ADR-002-미국-데이터소스-아키텍처]] 의 "가격 본격(M2)=Sharadar SEP" 결정을 **개정** — 가격 소스만 교체, 나머지 ADR-002 유효)
- **결정자**: 사용자 / Claude 협의

## 맥락 (Context)

M1 파일럿은 Tiingo 무료(현재상장만)로 검증 완료. M2(전체 유니버스·생존편향-correct 백테스트)엔 폐지종목 포함 가격이 필요한데 **미국 무료엔 폐지가격 소스가 없음**(구조적 비대칭, 무료 우회로 Quandl WIKI·yfinance·SimFin 모두 부적합). 유료 가성비 실측(워크플로우 `us-delisted-price-value`, 2026-06-16) 결과를 근거로 가격 소스를 확정한다. 전제: **재무는 EDGAR 무료 분담 → 가격 전용 최저가가 목표**(재무 번들 불필요).

## 결정 (Decision)

**M2 본격 가격 소스 = EODHD (EOD Historical Data), EOD All World 플랜($19.99/월 또는 $199/년).**
- raw OHLC(무수정) + adjusted_close(split+dividend) 분리 제공 → 우리 `원주가 + adj_factor` 모델 직결(adj_factor = adjusted/raw 역산 또는 Splits/Dividends API 결합).
- US 폐지종목 EOD 제공(2000~). 비폐지 상장종목 ~30년+. Linux/Docker 완전 호환(순수 REST + 공식 `eodhd` Python lib). 벌크 다운로드(거래소 전체 1요청).
- 키 = `.env` 의 `EODHD_API_KEY`(gitignore·이미지 미포함). 무료 티어(20콜/일)로 어댑터 개발·스모크, 본격 수집 시 유료 전환.

**history 정책**: 30년은 강제 목표 아님(예시였음). **데이터가 제공하는 가용 범위를 전부 사용** — 많을수록 백테스트 검증 정확도↑, 인위적 상한 없음. 백테스트 유효구간은 소스 보장 범위로 자연 결정(폐지 포함 분석은 2000~ 하한). [[plans/M1-데이터파이프라인]] §6 history 행 갱신.

## 검토한 대안 (Alternatives)

| 후보 | 2026 실가(가격전용) | 평가 |
|---|---|---|
| **EODHD** (채택) | $19.99/월 ($199/년) | 최저가급·raw/adjusted 분리·Linux·폐지 2000~. 가성비 1위 |
| FMP | $22/월(US)·$59(~30년) | raw 전용 엔드포인트·무료 Delisted API. 근소 2위 — 더 긴 history 필요 시 재검토 |
| Sharadar SEP | 비공개(로그인 게이트) | 데이터 골드스탠다드(21k+ survivorship-free·closeunadj raw·1998~)이나 가격 불투명 |
| Polygon/Massive | $29~79/월 | adjusted=split만(배당 수동)·리브랜딩 품질보고 → 하위 |

## 결과 (Consequences)

- **얻는 것**: 월 ~$20(가격만, 재무 EDGAR 무료)로 폐지 포함 survivorship-correct 백테스트 데이터. 어댑터 교체(EodhdSource)만으로 M1 파이프라인 재사용(DataSource Protocol).
- **감수하는 것**: 폐지 가격 2000~(그 이전 폐지 미보장 — history 정책상 허용). adj_factor 직접 미제공(raw/adjusted 역산 또는 Splits/Dividends 결합). 배당 데이터 업스트림 의존(채택 시 표본 검증). €/$ 표기 혼재(결제 통화 확인).
- **라이선스**: EOD All World = 개인·비배포 사용 범위. 해지/만료 후 데이터 삭제 의무 조항 존재(업계 표준) — **우리 재현성(스냅샷 안정·동일입력 동일결과)은 이 조항과 무관**(과거 EOD 불변 → 재구독 시 동일 데이터 재취득). 시스템엔 위반을 인코딩하지 않음(개인 운영 준수는 사용자 영역). 재배포는 금지.
- **재검토 트리거**: EODHD 폐지 커버리지·배당 정확도가 표본 검증서 미달이면 Sharadar SEP(데이터 최상, 실가 확인) 또는 FMP 재검토.

## 관련

- [[ADR-002-미국-데이터소스-아키텍처]](가격 graduation 개정) · [[2026-06-16-미국주식-데이터소스]] · [[plans/M1-데이터파이프라인]] §2 소스표
- 후속 사용자 액션: 본격 수집 전 EODHD 폐지티커 표본으로 가격 history 시작연도·완전성·배당 정확도 실측. 어댑터는 `historical raw` + `adjusted` 분리 엔드포인트 명시 사용.
