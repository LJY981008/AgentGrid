/**
 * 저수준 HTTP 클라이언트 — fetch 래퍼 + 에러 정규화.
 *
 * 설계 원칙(읽기 위주): 여기는 "서버에 묻고 응답을 그대로 받는" 얇은 층이다. 투자 계산은
 * 전혀 하지 않는다. 모든 실패를 ApiError 한 종류로 정규화해 화면이 일관되게 처리하도록 한다
 * (네트워크 끊김·타임아웃·4xx·5xx·JSON 파싱 실패 전부).
 *
 * 비유(Spring): RestTemplate/WebClient 의 공통 에러 핸들러를 한 곳에 모은 것.
 */

// 베이스 URL: 비어있으면 same-origin(빈 문자열) — dev 는 vite proxy 가, 운영은 리버스 프록시가
// /api 를 백엔드로 넘긴다. VITE_API_BASE 지정 시 절대 URL(끝 슬래시 제거).
const RAW_BASE = import.meta.env.VITE_API_BASE ?? "";
export const API_BASE = RAW_BASE.replace(/\/+$/, "");

/** HTTP 또는 네트워크 실패를 한 종류로 표현. status=0 = 네트워크/취소(응답 없음). */
export class ApiError extends Error {
  readonly status: number;
  /** rate limit(EODHD 무료 20콜/일 소진 등) — 화면이 친화 메시지로 분기. */
  readonly isRateLimited: boolean;
  /** 업스트림 인증 실패(키 문제) — 502 매핑. */
  readonly isUpstreamAuth: boolean;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.isRateLimited = status === 429;
    this.isUpstreamAuth = status === 502;
  }
}

function joinUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${p}`;
}

/** 서버 에러 본문에서 사람이 읽을 메시지 추출(FastAPI `detail` 우선). 키/토큰 비노출 가정(서버 책임). */
async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const data: unknown = await res.json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      return JSON.stringify(detail);
    }
  } catch {
    // 본문이 JSON 이 아니거나 비어있음 — 상태 코드 기반 기본 메시지로 폴백.
  }
  return `요청 실패 (HTTP ${res.status})`;
}

interface RequestOptions {
  method?: "GET" | "POST";
  /** POST 본문(JSON 직렬화). */
  body?: unknown;
  /** 쿼리 파라미터. undefined/null 값은 생략. */
  query?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
}

/** JSON 응답을 기대하는 요청. 실패는 전부 ApiError 로 던진다(화면은 try/catch 또는 훅이 흡수). */
export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, signal } = opts;

  let url = joinUrl(path);
  if (query) {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) sp.set(k, String(v));
    }
    const qs = sp.toString();
    if (qs) url += `?${qs}`;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    // 네트워크 끊김·CORS·취소 — 응답 자체가 없음(status=0).
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    const msg = err instanceof Error ? err.message : "네트워크 오류";
    throw new ApiError(`서버에 연결할 수 없습니다 (${msg})`, 0);
  }

  if (!res.ok) {
    throw new ApiError(await extractErrorMessage(res), res.status);
  }

  // 2xx 인데 본문이 비었거나 JSON 이 아니면 계약 위반 — 명확히 실패.
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError("응답을 해석할 수 없습니다 (JSON 아님)", res.status);
  }
}

/** 학습 정적 이미지의 절대 URL. react-markdown urlTransform 에서 상대 이미지 재작성에 사용. */
export function learningAssetUrl(relPath: string): string {
  const clean = relPath.replace(/^\/+/, "");
  return `${API_BASE}/learning-assets/${clean}`;
}
