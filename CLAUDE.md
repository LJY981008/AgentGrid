# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> ⚠️ 이 레포는 2026-06-16 **MCP 신뢰성 레지스트리 → 개인 투자용 미국 주식 분석(stockpick)** 으로 전환됐다(같은 날 한국→미국 2차 전환 [ADR-002] 포함). (디렉토리 경로/리모트 이름은 AgentGrid 유지 — 사용자 결정.)

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
| 웹앱(PWA) 작성·수정 (M3 — 구현 완료) | [.claude/rules/webapp-conventions.md](.claude/rules/webapp-conventions.md) | PWA·읽기 위주·투자 로직 프론트 중복 금지 |
| **외부 데이터 API 코드** (Tiingo·EODHD 등) | [.claude/rules/api-spec-reference.md](.claude/rules/api-spec-reference.md) + [docs/apis/](docs/apis/) | 캡처된 JSON 명세가 진실원천(엔드포인트·필드 환각 금지). 없으면 tech-researcher 재캡처(eodhd-spec-capture/tiingo-spec-capture). claude-api 스킬은 LLM 호출 시 |
| 버그·테스트/수집/백테스트 실패 | [debugging-discipline](.claude/skills/debugging-discipline/SKILL.md) | 추측 금지 + **이상결과 3분류**(버그/룩어헤드/생존편향) |
| 하네스 변경 | [harness-update](.claude/skills/harness-update/SKILL.md) | 분류→배치→drift 매핑 |
| 기획 작업 | `docs/plans/` (현황: [PLAN_STATUS.md](docs/plans/PLAN_STATUS.md)) | product-planner. 기준선 = stock-1st_plan |
| 스키마 변경 | **alembic 마이그레이션으로만** (`migrations/versions/` — [ADR-006](docs/decisions/ADR-006-PG스키마-alembic-첫실사용.md) 첫 실사용·`docker compose exec app alembic upgrade head`) | 직접 DDL 은 pre-bash-guard 차단. PG18 기능은 raw SQL(op.execute) |

---

## Project Overview

**stockpick** — 개인 투자용 **미국 주식(NYSE/NASDAQ/AMEX)** 분석. 과거 데이터로 **정량 룰 Top20** 생성 → **사용자 Claude 세션 토의로 수동 Top5** → 분산투자 → 추적·보정으로 안정화. AI 자동화는 미래 여지(우선순위 낮음). 1인용. ⚠️ 2026-06-16 한국→미국 시장 전환([ADR-002](docs/decisions/ADR-002-미국-데이터소스-아키텍처.md)) — 시장 무관 자산(BLOCKING·계약·스키마 PIT)은 유효, 소스·종목식별만 교체. 기획: [docs/plans/stock-1st_plan.md](docs/plans/stock-1st_plan.md)·[M1 스펙](docs/plans/M1-데이터파이프라인.md)

**Tech Stack** (2026-06-16 전환):
- Python ≥3.12 / **uv** + ruff + mypy(strict) + pytest — `pyproject.toml`, src 레이아웃(`src/stockpick/`)
- 데이터(미국): 가격 **Tiingo**(파일럿)→**EODHD**(M2, [ADR-003](docs/decisions/ADR-003-M2-가격소스-EODHD.md)) / 재무 **SEC EDGAR**(filed=PIT)+edgartools ([ADR-002](docs/decisions/ADR-002-미국-데이터소스-아키텍처.md)). 식별=SEC EDGAR `company_tickers.json`(ticker→cik, 키없음·User-Agent=EDGAR_IDENTITY / `data/edgar.py`·`EdgarSnapshotResolver`). 명세=[docs/apis/](docs/apis/). 키=.env(TIINGO_API_KEY·EODHD_API_KEY·EDGAR_IDENTITY[키 아님·신원]). (구 한국 FDR/pykrx/KRX 보류)
- 저장: **Parquet**(`pyarrow`, 1차 진실원본)+**DuckDB**(백테스트 스캔) + **PostgreSQL 18**(운영 서빙·**alembic**+**psycopg3** S5-a, 단방향 Parquet→PG 동기) — `compose.yaml`·`migrations/`. HTTP=`httpx`. TimescaleDB 비채택. 런타임 deps 는 `uv add` 실측 고정(uv.lock)
- API(M3): **FastAPI**+**uvicorn[standard]**(`src/stockpick/api/`) — 수집·랭킹·학습을 HTTP 노출. pydantic 응답계약 = 프론트 단일 출처. CORS=localhost:5173(컨테이너 내부 web). ⚠️ ranking `meta.validated=false`·키 비노출 — **validated=false 사유 = 백테스트 엔진은 구현(M2 골격)됐으나 현재 무료 1년치만 적재·S6 데이터 신뢰성 게이트 미통과라 룰 미입증. EODHD 결제 완료(2026-06-18 EOD Historical $19.99)됐으나 결제≠검증 — 다년 데이터 수집+S6 통과 전까지 false 고정**(§4.1 미검증 경고 상시)
- 웹앱(M3 — 구현 완료): PWA (`webapp/`) — **Vite8/React19/react-router7/TS**, 5 nav 화면(랭킹=Dashboard·데이터·유니버스·학습·백테스트 placeholder)+404
- 모듈 경계: `data`(수집·저장) / `rules`(Top20 랭킹) / `backtest`(검증 — M2 엔진 구현·골격, S6 게이트 후 신뢰) → `api`/`webapp`(상위 — 하위 조합) — 하위는 상위 import 금지

---

## Build & Development Commands

> 환경은 **Docker 기반 uv**(어디서 돌려도 동일 — `uv.lock` + 이미지 고정). 로컬 uv 설치 불필요.
> 베이스: `python:3.12-slim-trixie` + `ghcr.io/astral-sh/uv:0.11.21` 바이너리 주입, 2단계 sync(의존성/소스 레이어 분리), non-root. 상세 주석: `Dockerfile`.

```bash
docker compose up -d                               # 풀스택: postgres + app(FastAPI uvicorn:8000) + web(Vite dev)
#   브라우저 http://localhost:5174 (web 대시보드) · API 직접 http://localhost:8000 · postgres localhost:5433
#   ⚠️ 호스트 포트 리맵(타 프로젝트 AiCrawl 점유 실측): postgres 5432→5433·web 5173→5174 (컨테이너 내부 불변)
docker compose build app                           # 이미지 빌드(베이스 pull 네트워크 필요)

# ⚠️ 대용량 벌크 적재(data.bulk·다년 전체유니버스)는 상주 app(uvicorn)과 분리된 일회성 컨테이너로 실행.
#   상주 app 의 full_series() 전구간 메모리 로드(adapters.py)와 동시 가동 시 호스트 메모리 OOM
#   (2026-06-18 실측 ExitCode 137 — app mem_limit:12g 로 방어하나, 적재 자체는 API 와 격리가 정답).
docker compose stop app web                         # 상주 API·web 정지(메모리 경쟁 제거)
docker compose run -d --rm --no-deps --name stockpick-bulk app python -m stockpick.data.bulk  # 격리·detached·체크포인트 재개

# 검증은 app 컨테이너 안에서 — 소스는 ./src·./tests 바인드 마운트(수정 즉시 반영, editable 설치)
#   app 은 uvicorn(0.0.0.0:8000) 상주여도 exec 로 ruff/mypy/pytest·uv add 그대로 가능
docker compose exec app ruff check src tests       # 린트
docker compose exec app mypy                        # 타입(strict)
docker compose exec app pytest -q                   # 테스트
# 또는 일회성: docker compose run --rm app ruff check src tests

# 수집 Parquet 는 named volume(parquet-data) 영속 — app(uid 999) 소유, 컨테이너 재생성에도 유지
#   (호스트 바인드는 uid 불일치[호스트 1000 vs app 999]로 Parquet 쓰기 거부 → named volume 으로 회피)

# 개발 도구는 [dependency-groups].dev (PEP 735) — `uv sync` 가 기본 설치(extra 아님)
# 런타임 의존성 추가 시(실측 2026-06-16): compose 에 uv.lock 바인드 마운트가 없어 `exec ... uv add`
#   는 권한 거부됨(pyproject=호스트 1000 소유 vs uv.lock=이미지내 app 999 소유). 동작 절차:
#   docker compose run --rm --no-deps --user 1000:1000 -e UV_CACHE_DIR=/tmp/uvcache \
#     -v "$PWD/uv.lock:/app/uv.lock" app uv add --no-sync <pkg>   # 호스트 pyproject+uv.lock 갱신
#   docker compose build app && docker compose up -d --no-deps app  # .venv 반영(재생성)
.claude/hooks/tests/run.sh                         # 훅 회귀 테스트 (38케이스)
```

> 라이브 수집·파일럿: `app` 서비스가 `.env`(gitignore·이미지 미포함)의 `TIINGO_API_KEY` 를 interpolation 주입. 키 변경/추가 후 `docker compose up -d --no-deps app` 로 컨테이너 재생성해야 반영. 자동 테스트는 모킹이라 키 불요.
> uv.lock 재생성(로컬 uv 없음): `docker run --rm -v "$PWD":/app -w /app ghcr.io/astral-sh/uv:python3.12-trixie-slim uv lock`
> ⚠️ 호스트 5432 선점 시(다른 PG 컨테이너) `docker compose up -d` 충돌 — `--no-deps app` 로 app 만 띄우거나 포트 매핑 조정.

---

## 구조

| 경로 | 역할 |
|---|---|
| `Dockerfile` · `.dockerignore` | uv 기반 개발/실행 이미지(단일 FROM·2단계 uv sync로 의존성/소스 레이어 분리·non-root·BuildKit 캐시) |
| `compose.yaml` | `postgres`(PG18 운영) + `app`(FastAPI uvicorn:8000·소스 바인드·parquet-data named volume·`mem_limit:12g` OOM 방어) + `web`(node:22 Vite dev:5174→5173). ⚠️ 대용량 벌크는 app 격리 실행(위 Build 주석) |
| `uv.lock` | 의존성 고정(재현성 핵심) — 커밋 대상 |
| `migrations/` | alembic PG 마이그레이션(S5-a·ADR-006) — `env.py`(DATABASE_URL→psycopg3)·`versions/`. compose app 에 마운트. 직접 DDL 금지 |
| `src/stockpick/` | 도메인 계약(`types.py` = 기획 §6, **FinancialFact** 포함) + `data/`(수집·저장·`db.py` PG repo·Parquet→PG 단방향 동기·`export_stock_snapshot`(stock→JSON 스냅샷 S5-d)·`universe.py` 종목마스터 S5-b·`bulk.py` 다년 EOD 벌크 S5-c+**후처리 재구조화·`--finalize` 복구·commit 호출부 S5-d**)·`rules/` 모듈 + `backtest/`(M2 엔진 — `config·calendar·costs·strategy·ports·adapters·fakes·metrics·engine·benchmark·validation·demo`. 리밸·forward-return·폐지청산·IS/OOS·decay. **adapters `MasterUniverse`(종목마스터 기반 생존편향 유니버스·delisted_at+1 경계 S5-d)·`_select_universe`**) |
| `src/stockpick/api/` | FastAPI HTTP 층(M3, 상위 모듈) — `models.py`(pydantic 계약)·`deps.py`(DI·테스트 override)·`routes/{health,dataset,ingest,ranking,learning}.py`. `python -m stockpick.api` 기동 |
| `tests/` | pytest (픽스처·모킹 — 라이브 데이터 의존 금지) |
| `webapp/` | PWA 대시보드 (M3 활성) — Vite8/React19/router7/TS, `src/{api,components,pages}`. 5화면(랭킹·데이터·유니버스·학습·백테스트 placeholder). 읽기위주·투자로직 프론트 중복 금지([webapp-conventions](.claude/rules/webapp-conventions.md)) |
| `docs/` | **옵시디언 볼트** — plans·decisions·research·dev-log·work-history. MOC: [docs/HOME.md](docs/HOME.md) |
| `.github/` | CI (ruff/mypy/pytest + 훅 회귀) · 기본 브랜치 main |

---

## Subagents 인덱스 (.claude/agents/)

> 역할 분리: 기획↔구현↔스키마↔검증↔감사는 해당 에이전트로 위임. 결과만 메인으로.
> **⚠️ 서브에이전트 보고 규칙**: 부모에는 마지막 메시지만 전달 — 재호출(종료 촉구) 시 단답 금지, 최종 보고 전문 재출력. (OMC 4.14.6 에서 재호출 루프는 수정됨, 보험으로 유지)

**설계·구현**: `product-planner`(기획·마일스톤) · `python-expert`(데이터·랭킹·백테스트·API) · `db-architect`(PG·Parquet·시계열) · `devops-engineer`(compose·CI·uv) · `frontend-expert`(PWA 대시보드)
**검증·품질**: `test-engineer`(pytest·백테스트 가드) · `convention-reviewer`(rules 위반) · `security-reviewer`(API 키·의존성, 개인용이라 경량) · `qa-tester`(실동작) · `harness-auditor`(하네스 감사)
**리서치**: `tech-researcher`(데이터 API·퀀트 라이브러리·버전 — 학습데이터 불신)

## Skills 인덱스 (.claude/skills/)

- `/harness-update [요약?]` — 하네스 갱신 절차 / `debugging-discipline` — 실패 시 자동 매칭(이상결과 3분류)

---

## 환경 점검

- 세션은 git 루트(`/home/code/project/AgentGrid`)에서 시작 — rules 로드는 `.claude/hooks/.state/instructions-loaded.log` 실측
- 에이전트/훅 변경은 세션 재시작 후 반영, 스킬은 `/reload-skills`
