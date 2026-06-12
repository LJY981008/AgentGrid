---
name: debugging-discipline
description: Root-cause debugging protocol for AgentGrid. Use on any build failure, test failure, runtime error, or unexpected behavior BEFORE proposing fixes. No speculative fixes. Extra caution for Boot 4.x / Next 16 traps (APIs differ from training data). Trigger phrases - 버그, 에러, 빌드 실패, 테스트 실패, 왜 안 되지, 디버깅.
---

# debugging-discipline — 추측성 수정 금지 프로토콜

## 절차 (순서 엄수)

1. **증상 전부 수집** — 에러 메시지·스택 트레이스·로그를 원문 그대로. 요약/의역 금지
2. **데이터 흐름 역추적** — 증상 지점에서 입력 방향으로. 각 단계 실측 (로그/디버거/테스트)
3. **단일 가설 수립** — "아마 X 때문" 금지. 가설은 검증 가능한 형태로 1개씩
4. **최소 변경으로 검증** — 가설 1개 = 변경 1개 = 검증 1회. 여러 수정 동시 투입 금지
5. **3회 실패 시 중단** — 접근 자체를 재검토. 같은 부위 4번째 수정 시도 금지 (사용자에게 상황 보고)

## 이 프로젝트 특화 함정 (2026-06 신규 스택)

- **Boot 4.x ≠ 학습 데이터**: Jackson 3 (`tools.jackson`), 스타터 명칭(webmvc, per-module test starter), Testcontainers 2.x 패키지(`org.testcontainers.postgresql.*`). 컴파일 에러 시 추측 말고 의존성/패키지명 실측 (`./gradlew dependencies`)
- **Next 16 ≠ 학습 데이터**: `frontend/AGENTS.md` 경고 — `node_modules/next/dist/docs/` 동봉 문서가 1차 출처
- **버전 함정 의심 시**: WebSearch 로 2026-06 기준 재확인 — [[../../docs/research/2026-06-12-스택-버전-리서치|리서치 노트]] 선례 참조

## 검증 명령 (실측 수단)

```bash
cd backend && ./gradlew test --no-daemon            # Testcontainers 포함 통합 검증
cd backend && ./gradlew bootTestRun                 # compose 없이 앱 기동 (TC 자동)
docker compose logs -f --tail 100 postgres          # 인프라 로그 (redis/rabbitmq 동일)
cd frontend && npm run typecheck && npm run build   # 프론트 검증
curl -s localhost:8080/actuator/health | jq .       # 기동 상태
```

## 금지

- 에러 안 읽고 코드부터 수정
- "일반적으로 이렇게 한다"로 수정 근거 대체 (이 스택은 일반적이지 않음 — 신버전)
- 실패한 수정 되돌리지 않고 다음 수정 누적
