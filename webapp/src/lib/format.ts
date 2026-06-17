/**
 * 표시용 포맷 유틸 — 숫자·날짜를 일관되게 보여주기만 한다(계산/로직 아님).
 *
 * 투자 로직(점수·랭킹)은 전부 서버가 이미 계산해 내려준다. 여기서는 그 값을 사람이 읽기 좋게
 * 반올림·천단위 구분만. 절대 점수를 재계산하거나 순위를 다시 매기지 않는다(서버 = 단일 진실).
 */

/** 정수 천단위 구분(행수·거래량 등). null/undefined → "—". */
export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-US");
}

/** 소수 고정자리(점수 등). 기본 4자리. */
export function fmtNum(n: number | null | undefined, digits = 4): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** ISO 날짜 문자열 그대로 표시(null → "—"). 서버가 이미 YYYY-MM-DD 로 줌. */
export function fmtDate(d: string | null | undefined): string {
  return d ?? "—";
}

/** 퍼센트 표시(소수 입력 0.12 → "12.0%"). 모멘텀 팩터 등 비율값. */
export function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}
