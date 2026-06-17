/**
 * 학습 — 토픽 트리 + 마크다운 뷰어. 본인 투자 학습노트(docs/learning)를 앱에서 읽는다.
 *
 * 선택 문서는 URL 쿼리 `?path=` 로 관리한다 → 내부 .md 링크 이동·새로고침·딥링크가 자연 동작
 * (MarkdownView 의 urlTransform 이 만든 `/learn?path=` 와 일치). path 없으면 트리 첫 문서로 유도.
 */

import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router";
import { getLearningContent, getLearningTree } from "../api/endpoints";
import { useApi } from "../api/useApi";
import type { LearningNode } from "../api/types";
import { Empty, ErrorView, Loading } from "../components/common/StateViews";
import { TopicTree } from "../components/learning/TopicTree";
import { MarkdownView } from "../components/learning/MarkdownView";

/** 트리에서 첫 파일 노드의 path 를 찾는다(초기 진입 시 자동 선택). 00.* 정렬은 TopicTree 와 동일 기조. */
function firstFilePath(nodes: LearningNode[]): string | null {
  const sorted = [...nodes].sort((a, b) => {
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  for (const n of sorted) {
    if (n.type === "file") return n.path;
    const found = firstFilePath(n.children);
    if (found) return found;
  }
  return null;
}

export function LearningPage() {
  const [params, setParams] = useSearchParams();
  const activePath = params.get("path");

  const tree = useApi((signal) => getLearningTree(signal), []);

  // path 미지정 + 트리 로드 완료 → 첫 문서로 치환(replace, 히스토리 오염 방지).
  const fallbackPath = useMemo(
    () => (tree.data ? firstFilePath(tree.data.root) : null),
    [tree.data],
  );
  useEffect(() => {
    if (!activePath && fallbackPath) {
      setParams({ path: fallbackPath }, { replace: true });
    }
  }, [activePath, fallbackPath, setParams]);

  const content = useApi(
    (signal) => {
      if (!activePath) return Promise.reject(new Error("no path"));
      return getLearningContent(activePath, signal);
    },
    [activePath],
  );

  function selectDoc(path: string) {
    setParams({ path });
  }

  return (
    <div>
      <header className="page-head">
        <h1>학습</h1>
        <p>투자 학습노트 — 생존편향·룩어헤드 등 주의사항(00.caveats)을 먼저 읽으세요.</p>
      </header>

      {tree.loading && <Loading label="목차 불러오는 중…" />}
      {tree.error && <ErrorView error={tree.error} onRetry={tree.refetch} />}

      {tree.data && (
        <div className="learn-layout">
          {tree.data.root.length === 0 ? (
            <Empty>학습 노트가 없습니다(docs/learning 비어있음).</Empty>
          ) : (
            <>
              <TopicTree root={tree.data.root} activePath={activePath} onSelect={selectDoc} />
              <div className="card" style={{ minWidth: 0 }}>
                {!activePath && <Empty>왼쪽에서 문서를 선택하세요.</Empty>}
                {activePath && content.loading && <Loading />}
                {activePath && content.error && (
                  <ErrorView error={content.error} onRetry={content.refetch} />
                )}
                {activePath && content.data && !content.loading && !content.error && (
                  <MarkdownView content={content.data.content} dir={content.data.dir} />
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
