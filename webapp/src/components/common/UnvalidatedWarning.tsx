/**
 * 미검증 경고 배너 — §4.1 BLOCKING. 백테스트 검증 전 룰은 "알파"가 아님을 상시 표시한다.
 *
 * fail-safe 설계: meta 가 없거나(에러·로딩 실패) validated 가 true 가 아니면 **항상** 경고를
 * 띄운다. 즉 "검증됐다"는 신호가 명확히 올 때만 경고를 숨긴다 — 누락 시 위험을 과소표시하지
 * 않는다. 현재 서버 계약상 validated 는 항상 false 이므로 사실상 상시 노출.
 *
 * 비유(Spring): 결제 직전 "이 견적은 확정가 아님" 경고를 응답에 없더라도 기본 노출하는 것.
 */

export function UnvalidatedWarning({
  validated,
  warning,
}: {
  validated?: boolean;
  warning?: string;
}) {
  // validated === true 일 때만 숨김(그 외 undefined/false 전부 경고 — fail-safe).
  if (validated === true) return null;
  return (
    <div className="unvalidated-banner" role="note">
      <strong>⚠ 미검증 랭킹 — 투자 판단의 근거로 단독 사용 금지</strong>
      {warning ?? "백테스트 검증 전 — 알파 아님(stock-1st_plan §4.1)"}
    </div>
  );
}
