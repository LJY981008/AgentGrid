import type { Tool } from "./types";

/**
 * Mock 도구 8개 — 등급 분포 A:1 / B:2 / C:2 / D:2 / F:1.
 * 모든 finalScore 는 합산식(base = Σ축점수×가중치/100, +서킷브레이커 3, +llm delta)과 수식상 일치.
 * 엣지 케이스:
 *  - http-fetcher-mcp: 점수상 B(74) 인데 R2 치명 위반(타임아웃 0건) → 등급 상한 C (cap)
 *  - csv-tools-mcp: LLM 보정 미적용 (llmAdjustment: null)
 *  - postgres-mcp: 서킷 브레이커 보너스 +3
 */
export const mockTools: Tool[] = [
  {
    slug: "postgres-mcp",
    name: "postgres-mcp",
    description:
      "PostgreSQL 데이터베이스를 위한 MCP 서버. 스키마 조회·읽기 전용 쿼리·실행 계획 분석 tool 을 제공하며, 커넥션 풀과 서킷 브레이커로 DB 장애를 격리한다.",
    category: "DB 연동",
    language: "TypeScript",
    repoUrl: "https://github.com/acme-labs/postgres-mcp",
    grade: "A",
    finalScore: 95, // base 90 + CB 3 + LLM 2
    axisScores: [
      {
        id: "R1", label: "예외 처리", score: 92, weight: 25,
        evidences: [
          { ruleId: "TS-R1-001", file: "src/db/query.ts", line: 42, note: "DB 호출 26곳 중 24곳 try/catch 래핑 (적용률 92%)" },
          { ruleId: "TS-R1-003", file: "src/tools/explain.ts", line: 118, note: "catch 내 구조화 로깅 + MCP 에러 응답 변환 확인" },
        ],
      },
      {
        id: "R2", label: "타임아웃", score: 95, weight: 20,
        evidences: [
          { ruleId: "TS-R2-002", file: "src/db/pool.ts", line: 17, note: "pg Pool connectionTimeoutMillis/statement_timeout 설정 — 외부 호출 21곳 중 20곳 적용" },
        ],
      },
      {
        id: "R3", label: "재시도/백오프", score: 80, weight: 15,
        evidences: [
          { ruleId: "TS-R3-001", file: "src/db/retry.ts", line: 9, note: "p-retry 지수 백오프 + 최대 3회 — 읽기 쿼리에만 적용 (쓰기 제외 패턴 양호)" },
        ],
      },
      {
        id: "R4", label: "입력 검증", score: 88, weight: 15,
        evidences: [
          { ruleId: "TS-R4-001", file: "src/tools/index.ts", line: 31, note: "노출 tool 8개 전부 zod inputSchema 정의, 6개에 enum/min-max 제약 포함" },
        ],
      },
      {
        id: "R5", label: "의존성 건전성", score: 92, weight: 15,
        evidences: [
          { ruleId: "DEP-001", file: "package-lock.json", line: 1, note: "lockfile 존재, 버전 고정율 100%, OSV 대조 취약점 0건 (low 1건 -8 감점)" },
        ],
      },
      {
        id: "R6", label: "문서·메타데이터 품질", score: 90, weight: 10,
        evidences: [
          { ruleId: "DOC-001", file: "README.md", line: 1, note: "설치/설정/tool 목록/환경변수 섹션 모두 존재, LICENSE(MIT) 확인" },
        ],
      },
    ],
    capApplied: null,
    circuitBreakerBonus: true, // cockatiel CircuitBreakerPolicy 탐지 → +3
    llmAdjustment: {
      delta: 2,
      rationale:
        "트랜잭션 경계 내 예외 처리가 일관되며, 커넥션 풀 고갈 시 백오프 후 명시적 실패를 반환해 형식적 처리가 아님을 확인. 재시도가 읽기 전용 쿼리에만 적용되어 비멱등 연산 보호도 적절.",
      citations: [
        { file: "src/db/retry.ts", line: 14, quote: "if (!isReadOnly(sql)) return runOnce(sql); // 쓰기 쿼리는 재시도 제외" },
        { file: "src/db/pool.ts", line: 88, quote: "throw new PoolExhaustedError(...) // 풀 고갈을 삼키지 않고 전파" },
      ],
    },
    versions: { analyzer: "0.3.0", prompt: "1.0.0", model: "claude-sonnet-4-6" },
    commitHash: "a3f8c21d9e04b7f2c6a1e8d5b0934f7c2e6a1b8d",
    analyzedAt: "2026-06-10T14:22:00Z",
  },
  {
    slug: "browser-pilot",
    name: "browser-pilot",
    description:
      "Playwright 기반 브라우저 자동화 MCP 서버. 페이지 탐색·스크린샷·폼 입력 tool 을 제공하고, 페이지 로드 타임아웃과 셀렉터 대기 한도를 강제한다.",
    category: "브라우저 제어",
    language: "TypeScript",
    repoUrl: "https://github.com/pilotworks/browser-pilot",
    grade: "B",
    finalScore: 78, // base 75 + LLM 3
    axisScores: [
      {
        id: "R1", label: "예외 처리", score: 78, weight: 25,
        evidences: [
          { ruleId: "TS-R1-001", file: "src/actions/navigate.ts", line: 28, note: "브라우저 호출 18곳 중 14곳 처리 (적용률 78%) — 스크린샷 경로 2곳 미처리" },
        ],
      },
      {
        id: "R2", label: "타임아웃", score: 85, weight: 20,
        evidences: [
          { ruleId: "TS-R2-001", file: "src/browser/context.ts", line: 55, note: "page.goto/waitForSelector 에 timeout 옵션 — 외부 대기 지점 13곳 중 11곳 적용" },
        ],
      },
      {
        id: "R3", label: "재시도/백오프", score: 60, weight: 15,
        evidences: [
          { ruleId: "TS-R3-002", file: "src/actions/click.ts", line: 71, note: "커스텀 재시도 루프 — 최대 횟수는 있으나 고정 간격(백오프 없음)" },
        ],
      },
      {
        id: "R4", label: "입력 검증", score: 80, weight: 15,
        evidences: [
          { ruleId: "TS-R4-001", file: "src/tools/registry.ts", line: 19, note: "tool 10개 중 9개 inputSchema 정의, URL pattern 제약 포함" },
        ],
      },
      {
        id: "R5", label: "의존성 건전성", score: 70, weight: 15,
        evidences: [
          { ruleId: "DEP-002", file: "package.json", line: 24, note: "lockfile 존재, 와일드카드 버전 2건(^latest 류), moderate 취약점 1건" },
        ],
      },
      {
        id: "R6", label: "문서·메타데이터 품질", score: 70, weight: 10,
        evidences: [
          { ruleId: "DOC-001", file: "README.md", line: 1, note: "설치/tool 목록 있음, 환경변수 섹션 누락, LICENSE 존재" },
        ],
      },
    ],
    capApplied: null,
    circuitBreakerBonus: false,
    llmAdjustment: {
      delta: 3,
      rationale:
        "브라우저 크래시 시 컨텍스트를 재생성하고 세션 상태를 복원하는 복구 경로가 잘 설계됨 — 규칙 탐지 범위 밖의 실질적 견고성으로 판단.",
      citations: [
        { file: "src/browser/recovery.ts", line: 33, quote: "await this.recreateContext(session.snapshot()) // 크래시 후 상태 복원" },
      ],
    },
    versions: { analyzer: "0.3.0", prompt: "1.0.0", model: "claude-sonnet-4-6" },
    commitHash: "b7e2d94a1c58f3e6d0b9a4c7e2f1d8b5a3c6e9f2",
    analyzedAt: "2026-06-11T09:05:00Z",
  },
  {
    slug: "sqlite-bridge",
    name: "sqlite-bridge",
    description:
      "로컬 SQLite 파일을 노출하는 Python MCP 서버. pydantic 으로 쿼리 입력을 검증하고 읽기/쓰기 권한을 tool 단위로 분리한다.",
    category: "DB 연동",
    language: "Python",
    repoUrl: "https://github.com/dataworks-io/sqlite-bridge",
    grade: "B",
    finalScore: 73, // base 75 + LLM -2
    axisScores: [
      {
        id: "R1", label: "예외 처리", score: 80, weight: 25,
        evidences: [
          { ruleId: "PY-R1-001", file: "sqlite_bridge/db.py", line: 64, note: "I/O 지점 15곳 중 13곳 try/except — 전부 sqlite3.Error 등 구체 예외 (bare except 0건)" },
        ],
      },
      {
        id: "R2", label: "타임아웃", score: 75, weight: 20,
        evidences: [
          { ruleId: "PY-R2-003", file: "sqlite_bridge/db.py", line: 21, note: "sqlite3.connect(timeout=5.0) + busy_timeout PRAGMA — 장기 쿼리 한도는 미설정" },
        ],
      },
      {
        id: "R3", label: "재시도/백오프", score: 55, weight: 15,
        evidences: [
          { ruleId: "PY-R3-001", file: "sqlite_bridge/db.py", line: 88, note: "SQLITE_BUSY 재시도 루프 — 최대 횟수 있으나 백오프 미적용" },
        ],
      },
      {
        id: "R4", label: "입력 검증", score: 85, weight: 15,
        evidences: [
          { ruleId: "PY-R4-001", file: "sqlite_bridge/models.py", line: 12, note: "tool 6개 전부 pydantic 모델 검증, 테이블명 allowlist 제약 포함" },
        ],
      },
      {
        id: "R5", label: "의존성 건전성", score: 80, weight: 15,
        evidences: [
          { ruleId: "DEP-001", file: "uv.lock", line: 1, note: "uv.lock 존재, 버전 고정율 94%, 취약점 0건" },
        ],
      },
      {
        id: "R6", label: "문서·메타데이터 품질", score: 70, weight: 10,
        evidences: [
          { ruleId: "DOC-002", file: "README.md", line: 1, note: "설치/설정 있음, tool 설명 6개 중 4개만 기재" },
        ],
      },
    ],
    capApplied: null,
    circuitBreakerBonus: false,
    llmAdjustment: {
      delta: -2,
      rationale:
        "쓰기 tool 의 except 핸들러 2곳이 오류를 로깅만 하고 성공 응답을 반환 — 호출 측이 실패를 인지할 수 없는 형식적 처리로 판단.",
      citations: [
        { file: "sqlite_bridge/tools/write.py", line: 47, quote: "except sqlite3.Error as e:\n    logger.warning(e)\n    return {\"ok\": True}" },
      ],
    },
    versions: { analyzer: "0.3.0", prompt: "1.0.0", model: "claude-sonnet-4-6" },
    commitHash: "c1d8e5f2a9b4c7d0e3f6a9b2c5d8e1f4a7b0c3d6",
    analyzedAt: "2026-06-08T18:40:00Z",
  },
  {
    slug: "http-fetcher-mcp",
    name: "http-fetcher-mcp",
    description:
      "임의 HTTP API 를 호출해 응답을 정규화해 주는 범용 fetch MCP 서버. 스키마 검증과 예외 처리는 충실하지만 모든 외부 호출에 타임아웃이 없다.",
    category: "API 연동",
    language: "TypeScript",
    repoUrl: "https://github.com/netkit-dev/http-fetcher-mcp",
    grade: "C", // ⚠ 점수상 B(74) 이나 R2 치명 위반 cap 으로 C
    finalScore: 74, // base 75 + LLM -1 → 등급은 cap 적용
    axisScores: [
      {
        id: "R1", label: "예외 처리", score: 96, weight: 25,
        evidences: [
          { ruleId: "TS-R1-001", file: "src/fetcher.ts", line: 52, note: "fetch 호출 23곳 전부 try/catch + 오류 분류 래핑 (적용률 100%, 사소 감점 1건)" },
        ],
      },
      {
        id: "R2", label: "타임아웃", score: 0, weight: 20,
        evidences: [
          { ruleId: "TS-R2-000", file: "src/fetcher.ts", line: 52, note: "외부 네트워크 호출 23곳 중 타임아웃 설정 0건 — AbortSignal/timeout 옵션 미사용" },
          { ruleId: "TS-R2-000", file: "src/streaming.ts", line: 31, note: "스트리밍 응답 대기에도 한도 없음 — 원격 서버 무응답 시 무한 대기" },
        ],
      },
      {
        id: "R3", label: "재시도/백오프", score: 90, weight: 15,
        evidences: [
          { ruleId: "TS-R3-001", file: "src/retry.ts", line: 8, note: "async-retry 지수 백오프 + 최대 4회, 5xx 만 재시도 (4xx 제외 패턴 양호)" },
        ],
      },
      {
        id: "R4", label: "입력 검증", score: 95, weight: 15,
        evidences: [
          { ruleId: "TS-R4-001", file: "src/tools.ts", line: 15, note: "tool 4개 전부 zod 스키마 + URL pattern/메서드 enum 제약" },
        ],
      },
      {
        id: "R5", label: "의존성 건전성", score: 95, weight: 15,
        evidences: [
          { ruleId: "DEP-001", file: "pnpm-lock.yaml", line: 1, note: "lockfile 존재, 고정율 100%, 취약점 0건" },
        ],
      },
      {
        id: "R6", label: "문서·메타데이터 품질", score: 90, weight: 10,
        evidences: [
          { ruleId: "DOC-001", file: "README.md", line: 1, note: "필수 섹션 전부 존재, tool 설명 충실" },
        ],
      },
    ],
    capApplied: {
      axis: "R2",
      reason: "외부 네트워크 호출 23건이 존재하나 타임아웃 설정이 0건 — 원격 장애 시 무한 대기로 전파될 수 있는 치명 위반",
      maxGrade: "C",
    },
    circuitBreakerBonus: false,
    llmAdjustment: {
      delta: -1,
      rationale:
        "오류 분류는 정교하나 호출 결과를 무제한 메모리 버퍼에 적재 — 대용량 응답에서 자원 고갈 가능성을 경미한 감점으로 반영.",
      citations: [
        { file: "src/streaming.ts", line: 44, quote: "chunks.push(chunk) // 크기 상한 없는 누적 버퍼" },
      ],
    },
    versions: { analyzer: "0.3.0", prompt: "1.0.0", model: "claude-sonnet-4-6" },
    commitHash: "d4a7b0c3e6f9d2a5b8c1e4f7a0d3b6c9e2f5a8b1",
    analyzedAt: "2026-06-09T11:17:00Z",
  },
  {
    slug: "weather-mcp",
    name: "weather-mcp",
    description:
      "공개 기상 API 를 감싸는 Python MCP 서버. 기본적인 타임아웃은 있으나 예외 처리가 광역 except 위주이고 문서가 빈약하다.",
    category: "API 연동",
    language: "Python",
    repoUrl: "https://github.com/skylab-oss/weather-mcp",
    grade: "C",
    finalScore: 58, // base 57 + LLM 1
    axisScores: [
      {
        id: "R1", label: "예외 처리", score: 60, weight: 25,
        evidences: [
          { ruleId: "PY-R1-002", file: "weather_mcp/client.py", line: 38, note: "I/O 지점 10곳 중 8곳 처리, 단 광역 except Exception 4건 (-10×?건 감점 반영)" },
        ],
      },
      {
        id: "R2", label: "타임아웃", score: 70, weight: 20,
        evidences: [
          { ruleId: "PY-R2-001", file: "weather_mcp/client.py", line: 22, note: "requests.get(timeout=10) — 외부 호출 10곳 중 7곳 적용" },
        ],
      },
      {
        id: "R3", label: "재시도/백오프", score: 50, weight: 15,
        evidences: [
          { ruleId: "PY-R3-000", file: "weather_mcp/client.py", line: 1, note: "재시도 로직 미검출 — 중립 50점 (재시도가 항상 정답은 아님)" },
        ],
      },
      {
        id: "R4", label: "입력 검증", score: 50, weight: 15,
        evidences: [
          { ruleId: "PY-R4-002", file: "weather_mcp/server.py", line: 27, note: "tool 5개 중 3개 타입 힌트 시그니처만 — 범위/enum 제약 없음" },
        ],
      },
      {
        id: "R5", label: "의존성 건전성", score: 60, weight: 15,
        evidences: [
          { ruleId: "DEP-003", file: "requirements.txt", line: 1, note: "lockfile 없음(미고정 requirements), 취약점 0건 — lockfile 40점 미획득" },
        ],
      },
      {
        id: "R6", label: "문서·메타데이터 품질", score: 40, weight: 10,
        evidences: [
          { ruleId: "DOC-003", file: "README.md", line: 1, note: "설치 안내만 존재 — 설정/tool 목록/환경변수 섹션 누락" },
        ],
      },
    ],
    capApplied: null,
    circuitBreakerBonus: false,
    llmAdjustment: {
      delta: 1,
      rationale:
        "광역 except 가 많지만 모든 핸들러가 원인 메시지를 보존해 MCP 오류로 변환 — 침묵 삼킴(silent swallow)은 아니어서 소폭 상향.",
      citations: [
        { file: "weather_mcp/client.py", line: 41, quote: "raise McpError(f\"upstream failed: {e}\") from e" },
      ],
    },
    versions: { analyzer: "0.3.0", prompt: "1.0.0", model: "claude-sonnet-4-6" },
    commitHash: "e8b1c4d7f0a3e6b9c2d5f8a1b4e7c0d3f6a9b2c5",
    analyzedAt: "2026-06-07T08:55:00Z",
  },
  {
    slug: "csv-tools-mcp",
    name: "csv-tools-mcp",
    description:
      "CSV 파일 파싱·필터·집계 tool 을 제공하는 Python MCP 서버. 입력 검증이 거의 없고 대용량 파일 처리 한도가 없다.",
    category: "기타",
    language: "Python",
    repoUrl: "https://github.com/tabular-tools/csv-tools-mcp",
    grade: "D",
    finalScore: 45, // base 45, LLM 보정 미적용 (월 예산 소진 — 가드레일 #6)
    axisScores: [
      {
        id: "R1", label: "예외 처리", score: 45, weight: 25,
        evidences: [
          { ruleId: "PY-R1-003", file: "csv_tools/parser.py", line: 71, note: "파일 I/O 9곳 중 5곳 처리, except: pass(silent swallow) 1건 -10 감점" },
        ],
      },
      {
        id: "R2", label: "타임아웃", score: 50, weight: 20,
        evidences: [
          { ruleId: "PY-R2-002", file: "csv_tools/remote.py", line: 18, note: "원격 CSV 다운로드 2곳 중 1곳만 timeout 설정" },
        ],
      },
      {
        id: "R3", label: "재시도/백오프", score: 50, weight: 15,
        evidences: [
          { ruleId: "PY-R3-000", file: "csv_tools/remote.py", line: 1, note: "재시도 로직 미검출 — 중립 50점" },
        ],
      },
      {
        id: "R4", label: "입력 검증", score: 30, weight: 15,
        evidences: [
          { ruleId: "PY-R4-003", file: "csv_tools/server.py", line: 33, note: "tool 7개 중 3개만 타입 힌트 — 파일 경로 검증·크기 제약 전무" },
        ],
      },
      {
        id: "R5", label: "의존성 건전성", score: 55, weight: 15,
        evidences: [
          { ruleId: "DEP-002", file: "pyproject.toml", line: 14, note: "poetry.lock 존재하나 와일드카드 버전 3건, moderate 취약점 1건" },
        ],
      },
      {
        id: "R6", label: "문서·메타데이터 품질", score: 35, weight: 10,
        evidences: [
          { ruleId: "DOC-003", file: "README.md", line: 1, note: "한 단락 소개뿐 — LICENSE 없음, tool 설명 부재" },
        ],
      },
    ],
    capApplied: null,
    circuitBreakerBonus: false,
    llmAdjustment: null, // ⚠ LLM 보정 미적용 — 월 예산 소진으로 규칙 점수만 산출 (가드레일 #6 실패 격리)
    versions: { analyzer: "0.3.0", prompt: "1.0.0", model: "claude-sonnet-4-6" },
    commitHash: "f2c5d8e1a4b7f0c3d6e9a2b5c8f1d4e7a0b3c6d9",
    analyzedAt: "2026-06-06T21:30:00Z",
  },
  {
    slug: "redis-inspector",
    name: "redis-inspector",
    description:
      "Redis 키 탐색·TTL 점검·메모리 분석 MCP 서버. 연결 실패 시 고정 간격 무한 재시도 루프가 있어 retry storm 위험이 탐지됐다.",
    category: "DB 연동",
    language: "TypeScript",
    repoUrl: "https://github.com/cachecrew/redis-inspector",
    grade: "D",
    finalScore: 44, // base 47 + LLM -3
    axisScores: [
      {
        id: "R1", label: "예외 처리", score: 56, weight: 25,
        evidences: [
          { ruleId: "TS-R1-002", file: "src/redis/client.ts", line: 90, note: "Redis 호출 16곳 중 11곳 처리, 빈 catch 2건 -20 감점" },
        ],
      },
      {
        id: "R2", label: "타임아웃", score: 45, weight: 20,
        evidences: [
          { ruleId: "TS-R2-002", file: "src/redis/client.ts", line: 12, note: "connectTimeout 만 설정 — 명령 단위 타임아웃은 14곳 중 5곳" },
        ],
      },
      {
        id: "R3", label: "재시도/백오프", score: 20, weight: 15,
        evidences: [
          { ruleId: "TS-R3-003", file: "src/redis/reconnect.ts", line: 27, note: "while(true) + 고정 500ms 재연결 루프 — 무한/고정간격 재시도(retry storm 위험) 20점" },
        ],
      },
      {
        id: "R4", label: "입력 검증", score: 50, weight: 15,
        evidences: [
          { ruleId: "TS-R4-002", file: "src/tools.ts", line: 44, note: "tool 6개 중 4개 스키마 정의 — 키 패턴(glob) 입력 무검증 2건" },
        ],
      },
      {
        id: "R5", label: "의존성 건전성", score: 60, weight: 15,
        evidences: [
          { ruleId: "DEP-002", file: "package.json", line: 19, note: "lockfile 존재, deprecated 패키지 1건, moderate 취약점 1건" },
        ],
      },
      {
        id: "R6", label: "문서·메타데이터 품질", score: 45, weight: 10,
        evidences: [
          { ruleId: "DOC-002", file: "README.md", line: 1, note: "설치 안내·LICENSE 존재, 환경변수/tool 목록 누락" },
        ],
      },
    ],
    capApplied: null,
    circuitBreakerBonus: false,
    llmAdjustment: {
      delta: -3,
      rationale:
        "무한 재연결 루프가 jitter 없이 모든 클라이언트에서 동시 발화하는 구조 — Redis 복구 시점에 부하가 집중되는 전형적 retry storm 패턴으로 추가 감점.",
      citations: [
        { file: "src/redis/reconnect.ts", line: 29, quote: "await sleep(500); continue; // 백오프·jitter·상한 없음" },
      ],
    },
    versions: { analyzer: "0.3.0", prompt: "1.0.0", model: "claude-sonnet-4-6" },
    commitHash: "a9d2e5f8b1c4d7e0f3a6b9c2d5e8f1a4b7c0d3e6",
    analyzedAt: "2026-06-05T16:12:00Z",
  },
  {
    slug: "quick-scraper",
    name: "quick-scraper",
    description:
      "URL 을 받아 본문 텍스트를 추출하는 스크래핑 MCP 서버. 예외 처리·타임아웃·검증이 전반적으로 부재한 스크립트 수준 구현.",
    category: "브라우저 제어",
    language: "Python",
    repoUrl: "https://github.com/hobbyhacks/quick-scraper",
    grade: "F",
    finalScore: 21, // base 26 + LLM -5
    axisScores: [
      {
        id: "R1", label: "예외 처리", score: 25, weight: 25,
        evidences: [
          { ruleId: "PY-R1-003", file: "scraper.py", line: 12, note: "I/O 지점 8곳 중 3곳만 처리, bare except 2건·except: pass 1건 -30 감점" },
        ],
      },
      {
        id: "R2", label: "타임아웃", score: 30, weight: 20,
        evidences: [
          { ruleId: "PY-R2-001", file: "scraper.py", line: 9, note: "외부 호출 7곳 중 2곳만 timeout — 나머지는 무한 대기 가능" },
        ],
      },
      {
        id: "R3", label: "재시도/백오프", score: 20, weight: 15,
        evidences: [
          { ruleId: "PY-R3-003", file: "scraper.py", line: 48, note: "실패 시 즉시 재호출 3중 중첩 루프 — 고정간격/상한 불명확, retry storm 위험" },
        ],
      },
      {
        id: "R4", label: "입력 검증", score: 15, weight: 15,
        evidences: [
          { ruleId: "PY-R4-003", file: "server.py", line: 8, note: "tool 3개 전부 스키마 없음 — URL 형식 검증조차 부재 (SSRF 표면)" },
        ],
      },
      {
        id: "R5", label: "의존성 건전성", score: 40, weight: 15,
        evidences: [
          { ruleId: "DEP-003", file: "requirements.txt", line: 1, note: "lockfile 없음, latest 지정 2건, high 취약점 1건 -15" },
        ],
      },
      {
        id: "R6", label: "문서·메타데이터 품질", score: 25, weight: 10,
        evidences: [
          { ruleId: "DOC-003", file: "README.md", line: 1, note: "2줄 README — LICENSE·tool 설명·환경변수 전부 부재" },
        ],
      },
    ],
    capApplied: null,
    circuitBreakerBonus: false,
    llmAdjustment: {
      delta: -5,
      rationale:
        "추출 실패 시 빈 문자열을 정상 결과로 반환해 호출 에이전트가 오류를 인지할 수 없음 — 신뢰성 관점에서 가장 위험한 침묵 실패 패턴.",
      citations: [
        { file: "scraper.py", line: 55, quote: "except:\n    return \"\"  # 실패를 빈 본문으로 위장" },
      ],
    },
    versions: { analyzer: "0.3.0", prompt: "1.0.0", model: "claude-sonnet-4-6" },
    commitHash: "b3e6f9a2c5d8e1f4a7b0c3d6e9f2a5b8c1d4e7f0",
    analyzedAt: "2026-06-04T13:48:00Z",
  },
];

export function findToolBySlug(slug: string): Tool | undefined {
  return mockTools.find((t) => t.slug === slug);
}
