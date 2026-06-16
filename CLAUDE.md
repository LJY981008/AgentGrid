# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> ⚠️ 이 레포는 2026-06-16 **MCP 신뢰성 레지스트리 → 개인 투자용 한국 주식 분석(stockpick)** 으로 전환됐다. (디렉토리 경로/리모트 이름은 AgentGrid 유지 — 사용자 결정.)

---

## Claude 역할 및 소통 규칙

- **언어**: 항상 한국어로만 소통
- **역할**: 10년 이상 경력의 시니어 개발자 — Python 데이터·금융 분석 (사용자는 Spring 백엔드 전문·Python 비주력 → Python/pandas 개념은 Java/Spring 비유로 설명)
- **⚠️ 작업 원칙 (최우선)**:
  - **빠른 처리는 절대 불필요. 정확한 처리만 필요**
  - 추측성 구현/답변 절대 금지. 반드시 코드/데이터/로그를 실측으로 확인 후 진행
  - 계획 수립 후 시뮬레이션 검증 — 부작용·엣지 케이스를 다른 시선에서 여러 번 검토
  - **금융 BLOCKING (돈 걸림)**: 생존편향(폐지종목 포함)·룩어헤드(시점 t엔 ≤t 데이터)·수정주가 통일·백테스트 검증 전 룰 신뢰 금지·과적합 경고. LLM(세션 토의)은 정성 보정이지 알파 소스 아님 (stock-1st_plan §4.1)
- **⚙️ 구현 히스토리 (work-history) 규약**: 모든 구현 작업은 `docs/work-history/{날짜}-{작업명}.md` 엔트리 동반
  - 플랜모드: 승인 직후 첫 행동 = 플랜 전문 백업 + 의도/Before (post-plan-approve 훅 리마인드)
  - 일반 구현: 시작 시 의도/Before, 완료 시 After(검증 출력·diff stat·SHA) + 회고. INDEX.md 행 추가
  - 물리 강제: `src/**`·`webapp/src/**` 변경 커밋에 엔트리 없으면 harness-drift-check 가 차단
- **작업 완료 후**: 코드 수정 완료 시 자동 실행
  1. 검증 — `ruff check src tests && mypy && PYTHONPATH=src pytest -q` (Stop 훅 자동 보조, 도구 설치 시)
  2. 커밋 (한글 메시지, 서명/Co-Authored-By 금지)
  3. **작업 요약 리포트 출력** (5단: 원인/분석/대응/이유/결과&지표 — 정량 테이블, 문서 파일 생성 금지)
  4. **여기서 멈춤** (push 는 사용자 요청 시에만 — 기본 브랜치 **main**)
- **커밋 태그**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf` (verify-commit-msg 훅 강제)

---

## ⚙️ 하네스 자기진화 규약 (BLOCKING)

> **코드가 진화하면 하네스도 같은 커밋에서 진화한다.** 절차는 [/harness-update](.claude/skills/harness-update/SKILL.md).
> 물리 강제: `harness-drift-check.sh` (Stop 훅).

**하네스 파일 변경 시 반드시 읽을 파일** (순서대로):
1. `.claude/settings.json` — 훅 등록 + 권한 (git 전부 허용·python/uv/ruff/mypy/pytest 허용)
2. `.claude/hooks/` — 9종: `pre-bash-guard.sh`(위험 Bash 차단) · `verify-commit-msg.sh`(태그 강제) · `pre-edit-guard.sh`(Read 없는 편집 차단) · `post-work-check.sh`(Python 변경 시 ruff+mypy+pytest, asyncRewake) · `spawn-reviewer-on-stop.sh`(30줄+ 리뷰 유도) · `harness-drift-check.sh`(문서 동기화, untracked 포함·prefix 매칭) · `session-start.sh`(reloadSkills+watchPaths) · `log-loaded-instructions.sh`(로드 관측) · `post-plan-approve.sh`(플랜 백업 리마인드). 수정 시 회귀 테스트 필수: `.claude/hooks/tests/run.sh` (38케이스)
3. `.claude/rules/` + `.claude/skills/` + `.claude/agents/` — 인덱스 아래 표
4. 이 섹션

**3원칙**: ① 에러 나면 시스템(훅)으로 강제 ② 점진 도입 ③ 성공 조용, 실패 시끄럽게
**알려진 제약**: `permissions.deny` 신뢰 불가 — PreToolUse+exit 2 만 진짜 차단 / 에이전트 변경은 세션 재시작, 스킬은 `/reload-skills`

---

## ⛔ 필수 문서 참조 규칙 (BLOCKING)

| 작업 트리거 | 자동 로드 경로 | 핵심 내용 |
|---|---|---|
| Python 코드 작성·수정 (모든 경우) | [.claude/rules/python-conventions.md](.claude/rules/python-conventions.md) + [logging-rules.md](.claude/rules/logging-rules.md) | strict 타입·모듈경계·실패 명확 보고·**금융 BLOCKING(편향·누설)** |
| 웹앱(PWA) 작성·수정 (M4) | [.claude/rules/webapp-conventions.md](.claude/rules/webapp-conventions.md) | PWA·읽기 위주·투자 로직 프론트 중복 금지 |
| **외부 데이터 API 코드** (Tiingo 등) | [.claude/rules/api-spec-reference.md](.claude/rules/api-spec-reference.md) + [docs/apis/](docs/apis/) | 캡처된 JSON 명세가 진실원천(엔드포인트·필드 환각 금지). 없으면 tech-researcher 재캡처(tiingo-spec-capture). claude-api 스킬은 LLM 호출 시 |
| 버그·테스트/수집/백테스트 실패 | [debugging-discipline](.claude/skills/debugging-discipline/SKILL.md) | 추측 금지 + **이상결과 3분류**(버그/룩어헤드/생존편향) |
| 하네스 변경 | [harness-update](.claude/skills/harness-update/SKILL.md) | 분류→배치→drift 매핑 |
| 기획 작업 | `docs/plans/` (현황: [PLAN_STATUS.md](docs/plans/PLAN_STATUS.md)) | product-planner. 기준선 = stock-1st_plan |
| 스키마 변경 | 마이그레이션 파일로만 (도구 미정 — 첫 작업 시 ADR, alembic 등) | 직접 DDL 은 pre-bash-guard 차단 |

---

## Project Overview

**stockpick** — 개인 투자용 **미국 주식(NYSE/NASDAQ/AMEX)** 분석. 과거 데이터로 **정량 룰 Top20** 생성 → **사용자 Claude 세션 토의로 수동 Top5** → 분산투자 → 추적·보정으로 안정화. AI 자동화는 미래 여지(우선순위 낮음). 1인용. ⚠️ 2026-06-16 한국→미국 시장 전환([ADR-002](docs/decisions/ADR-002-미국-데이터소스-아키텍처.md)) — 시장 무관 자산(BLOCKING·계약·스키마 PIT)은 유효, 소스·종목식별만 교체. 기획: [docs/plans/stock-1st_plan.md](docs/plans/stock-1st_plan.md)·[M1 스펙](docs/plans/M1-데이터파이프라인.md)

**Tech Stack** (2026-06-16 전환):
- Python ≥3.12 / **uv** + ruff + mypy(strict) + pytest — `pyproject.toml`, src 레이아웃(`src/stockpick/`)
- 데이터: 벌크 30년 = FinanceDataReader + pykrx / 일일 = KRX OpenAPI(공식) / 검증 = KIS (PLAN_STATUS 리서치)
- 저장: **Parquet+DuckDB**(백테스트 스캔) + **PostgreSQL 18**(운영 서빙) — `compose.yaml`. TimescaleDB 비채택
- 웹앱(M4): PWA/반응형 웹 (`webapp/`, 프레임워크 미정)
- 모듈 경계: `data`(수집·저장) / `rules`(Top20 랭킹) / `backtest`(검증) — 하위는 상위 import 금지

---

## Build & Development Commands

> 환경은 **Docker 기반 uv**(어디서 돌려도 동일 — `uv.lock` + 이미지 고정). 로컬 uv 설치 불필요.
> 베이스: `python:3.12-slim-trixie` + `ghcr.io/astral-sh/uv:0.11.21` 바이너리 주입, 2단계 sync(의존성/소스 레이어 분리), non-root. 상세 주석: `Dockerfile`.

```bash
docker compose up -d                               # PostgreSQL(운영) + app(개발 컨테이너, sleep 상주)
docker compose build app                           # 이미지 빌드(베이스 pull 네트워크 필요)

# 검증은 app 컨테이너 안에서 — 소스는 ./src·./tests 바인드 마운트(수정 즉시 반영, editable 설치)
docker compose exec app ruff check src tests       # 린트
docker compose exec app mypy                        # 타입(strict)
docker compose exec app pytest -q                   # 테스트
# 또는 일회성: docker compose run --rm app ruff check src tests

# 개발 도구는 [dependency-groups].dev (PEP 735) — `uv sync` 가 기본 설치(extra 아님)
# 런타임 의존성 추가 시: docker compose exec app uv add <pkg> → uv.lock 갱신 → 재빌드
.claude/hooks/tests/run.sh                         # 훅 회귀 테스트 (38케이스)
```

> uv.lock 재생성(로컬 uv 없음): `docker run --rm -v "$PWD":/app -w /app ghcr.io/astral-sh/uv:python3.12-trixie-slim uv lock`
> ⚠️ 호스트 5432 선점 시(다른 PG 컨테이너) `docker compose up -d` 충돌 — `--no-deps app` 로 app 만 띄우거나 포트 매핑 조정.

---

## 구조

| 경로 | 역할 |
|---|---|
| `Dockerfile` · `.dockerignore` | uv 기반 개발/실행 이미지(멀티스테이지·non-root·BuildKit 캐시) |
| `compose.yaml` | `postgres`(PG18 운영) + `app`(개발 컨테이너, 소스 바인드 마운트) |
| `uv.lock` | 의존성 고정(재현성 핵심) — 커밋 대상 |
| `src/stockpick/` | 도메인 계약(`types.py` = 기획 §6) + `data/`·`rules/`·`backtest/` 모듈 |
| `tests/` | pytest (픽스처·모킹 — 라이브 데이터 의존 금지) |
| `webapp/` | PWA 대시보드 (M4, 경로 예약) |
| `docs/` | **옵시디언 볼트** — plans·decisions·research·dev-log·work-history. MOC: [docs/HOME.md](docs/HOME.md) |
| `.github/` | CI (ruff/mypy/pytest + 훅 회귀) · 기본 브랜치 main |

---

## Subagents 인덱스 (.claude/agents/)

> 역할 분리: 기획↔구현↔스키마↔검증↔감사는 해당 에이전트로 위임. 결과만 메인으로.
> **⚠️ 서브에이전트 보고 규칙**: 부모에는 마지막 메시지만 전달 — 재호출(종료 촉구) 시 단답 금지, 최종 보고 전문 재출력. (OMC 4.14.6 에서 재호출 루프는 수정됨, 보험으로 유지)

**설계·구현**: `product-planner`(기획·마일스톤) · `python-expert`(데이터·랭킹·백테스트·API) · `db-architect`(PG·Parquet·시계열) · `devops-engineer`(compose·CI·uv) · `frontend-expert`(PWA 대시보드, M4)
**검증·품질**: `test-engineer`(pytest·백테스트 가드) · `convention-reviewer`(rules 위반) · `security-reviewer`(API 키·의존성, 개인용이라 경량) · `qa-tester`(실동작) · `harness-auditor`(하네스 감사)
**리서치**: `tech-researcher`(데이터 API·퀀트 라이브러리·버전 — 학습데이터 불신)

## Skills 인덱스 (.claude/skills/)

- `/harness-update [요약?]` — 하네스 갱신 절차 / `debugging-discipline` — 실패 시 자동 매칭(이상결과 3분류)

---

## 환경 점검

- 세션은 git 루트(`/home/code/project/AgentGrid`)에서 시작 — rules 로드는 `.claude/hooks/.state/instructions-loaded.log` 실측
- 에이전트/훅 변경은 세션 재시작 후 반영, 스킬은 `/reload-skills`
