import DirectoryExplorer from "@/components/DirectoryExplorer";
import { mockTools } from "@/lib/mock/tools";

/**
 * 디렉토리 (F3) — 서버 컴포넌트가 목록 데이터를 공급하고,
 * 검색/필터/정렬 인터랙션은 DirectoryExplorer("use client")가 담당.
 * 실제 구현 시 mockTools 자리가 Spring Boot API fetch 로 교체된다.
 */
export default function DirectoryPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">도구 디렉토리</h1>
        <p className="mt-1.5 text-sm text-zinc-600 dark:text-zinc-400">
          제출된 MCP 서버를 정적 분석해 시스템 신뢰성 등급(A~F)과 산출 근거를
          공개합니다. 카드를 클릭하면 축별 점수와 발동 규칙 근거를 볼 수 있습니다.
        </p>
      </div>
      <DirectoryExplorer tools={mockTools} />
    </div>
  );
}
