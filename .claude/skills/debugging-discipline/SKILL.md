---
name: debugging-discipline
description: Root-cause debugging protocol for stockpick. Use on any error, test failure, data pipeline failure, or unexpected backtest result BEFORE proposing fixes. No speculative fixes. Finance-specific - distinguish code-bug vs data-issue vs look-ahead/survivorship artifact. Trigger phrases - 버그, 에러, 테스트 실패, 수집 실패, 백테스트 이상, 왜 안 되지, 디버깅.
---

# debugging-discipline — 추측성 수정 금지 프로토콜

## 절차 (순서 엄수)

1. **증상 전부 수집** — 에러·스택·로그·실패 데이터 원문 그대로. 요약/의역 금지
2. **데이터 흐름 역추적** — 증상 지점에서 입력 방향으로. 각 단계 실측
3. **단일 가설** — "아마 X" 금지. 검증 가능한 형태로 1개씩
4. **최소 변경 검증** — 가설 1 = 변경 1 = 검증 1
5. **3회 실패 시 중단** — 접근 재검토, 사용자 보고

## 금융 도메인 특화: 이상 결과 3분류 먼저

백테스트·랭킹 결과가 "이상하게 좋으면" **버그가 아니라 데이터 함정**일 가능성 — 수정 전 분류:

| 분류 | 판별 | 대응 |
|---|---|---|
| ① 코드 버그 | 동일 입력 재현, 로직 추적으로 원인 | 코드 수정 |
| ② 룩어헤드 누설 | 수익률 비현실적으로 높음 + 시점 t 결정에 t 이후 데이터 사용 | 데이터 시점 경계 수정 (≤t 만) |
| ③ 생존편향 | 폐지종목 누락된 유니버스로 과거 계산 | 폐지종목 포함 데이터로 재실행 |

②③을 ①로 착각해 "수익률 잘 나오니 통과"가 이 도메인 최악의 실수 — **너무 좋은 결과를 의심**하라.

## 데이터 실패도 분류

| 분류 | 판별 | 대응 |
|---|---|---|
| 소스 차단 | 403/빈 응답, 타 종목 정상 | 코드 수정 금지 — rate limit·재시도 (FDR/pykrx 비공식) |
| 소스 데이터 결함 | 특정 종목·기간만 결측/이상값 | 교차검증(다른 소스)·보정 기록 |
| 우리 파싱 버그 | 픽스처 테스트도 실패 | 코드 수정 |

## 검증 명령

```bash
ruff check src tests && mypy && PYTHONPATH=src pytest -q   # 전체
PYTHONPATH=src python3 -c "from stockpick.types import ..."  # 계약 import
docker compose logs -f postgres                              # 인프라
python3 -m stockpick... <스크립트>                          # 단건 재현
```

## 금지

- 에러 안 읽고 수정 / 실패 수정 누적 / 차단(소스)을 우회 기법으로 해결 → 실패 보고가 정답
- 라이브러리(pandas·pykrx) API 추측 — 실측·tech-researcher
