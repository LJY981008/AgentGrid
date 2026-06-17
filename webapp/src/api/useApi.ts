/**
 * 데이터 페칭 훅 — 로딩/에러/데이터 3상태를 정규화.
 *
 * 라이브러리(react-query 등) 없이 1인용 대시보드에 충분한 최소 구현. 마운트 시 1회 호출,
 * AbortController 로 언마운트 시 취소. 수동 재조회(refetch) 제공. 추가 의존성 없음(단순 우선).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./client";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
  /** 수동 재조회(데이터 수집 후 랭킹 갱신 등). */
  refetch: () => void;
}

/**
 * @param fetcher AbortSignal 을 받아 Promise 를 반환하는 함수. deps 가 바뀌면 재호출.
 * @param deps 의존성 — 바뀌면 자동 재조회(쿼리 파라미터 변경 등).
 */
export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[] = [],
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [tick, setTick] = useState(0);

  // fetcher 는 매 렌더 새로 만들어질 수 있으므로 ref 로 고정(deps 만 재조회 트리거로 사용).
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetcherRef.current(controller.signal).then(
      (result) => {
        if (!controller.signal.aborted) {
          setData(result);
          setLoading(false);
        }
      },
      (err: unknown) => {
        if (controller.signal.aborted) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(
          err instanceof ApiError ? err : new ApiError("알 수 없는 오류", 0),
        );
        setLoading(false);
      },
    );

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, refetch };
}
