/**
 * 마크다운 렌더 — react-markdown 10 + remark-gfm(표·체크박스) + rehype-slug(heading id → #앵커).
 *
 * ⭐ 상대경로 재작성은 react-markdown 10 의 `urlTransform` prop 으로 한다(커스텀 rehype 플러그인
 * 금지 — tech-researcher 권고). urlTransform 은 모든 href/src 에 대해 호출되며 반환값이 최종 URL.
 *
 * 재작성 규칙(이 문서의 디렉토리 dir 기준):
 *  - 절대 URL(http/https) · 프로토콜(mailto: 등) · 페이지내 앵커(#...) → 그대로(화이트리스트, XSS 방어).
 *  - 상대 이미지(![](assets/x.png)) → `${API_BASE}/learning-assets/${dir}/x.png` (정적 이미지 서빙).
 *  - 상대 .md 링크([x](other.md)) → 내부 라우트 `/learn?path=<해소된 상대경로>` (앱 내 이동).
 *  - 그 외 상대 링크 → dir 기준으로 합쳐 학습 asset 으로(잡다한 첨부).
 *
 * ⚠️ react-markdown 의 기본 urlTransform 은 안전하지 않은 스킴(javascript: 등)을 제거한다. 우리가
 * urlTransform 을 덮어쓰므로, 절대/프로토콜 URL 은 안전한 스킴만 통과시키고 나머지는 비운다.
 */

import { useMemo } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import { useNavigate } from "react-router";
import { learningAssetUrl } from "../../api/client";

const SAFE_PROTOCOLS = new Set(["http:", "https:", "mailto:", "tel:"]);

/** 상대경로를 dir 기준으로 정규화(.. / . 해소). 학습 트리 내부 경로 문자열을 만든다. */
function resolveRelative(dir: string, rel: string): string {
  const base = dir ? dir.split("/") : [];
  const parts = rel.split("/");
  const stack = [...base];
  for (const p of parts) {
    if (p === "" || p === ".") continue;
    if (p === "..") stack.pop();
    else stack.push(p);
  }
  return stack.join("/");
}

/** 절대/프로토콜 URL 의 안전성 검사. 안전하면 그대로, 아니면 빈 문자열(차단). */
function sanitizeAbsolute(url: string): string {
  try {
    const u = new URL(url, "https://placeholder.invalid");
    // 원본이 절대(스킴 포함)였는지 판단: 스킴이 placeholder 가 아니면 절대.
    if (/^[a-z][a-z0-9+.-]*:/i.test(url)) {
      return SAFE_PROTOCOLS.has(u.protocol) ? url : "";
    }
  } catch {
    return "";
  }
  return url;
}

function makeUrlTransform(dir: string) {
  // url: 원본 href/src, key: "href" | "src", node 는 사용 안 함.
  return (url: string): string => {
    if (!url) return url;

    // 페이지 내 앵커 — 그대로(rehype-slug 가 만든 heading id 로 점프).
    if (url.startsWith("#")) return url;

    // 절대 URL · 프로토콜 — 안전 스킴만 통과(XSS 방어).
    if (/^[a-z][a-z0-9+.-]*:/i.test(url) || url.startsWith("//")) {
      return sanitizeAbsolute(url.startsWith("//") ? `https:${url}` : url);
    }

    // 루트 절대경로(/foo) — 학습 자산 루트 기준으로.
    const isRootAbsolute = url.startsWith("/");

    // 앵커가 붙은 상대 .md 링크 분리(other.md#section).
    const [pathPart, hash = ""] = url.split("#");
    const resolved = isRootAbsolute
      ? pathPart.replace(/^\/+/, "")
      : resolveRelative(dir, pathPart);

    // 상대 .md 링크 → 내부 라우트(앱 내 이동). 클릭 핸들러가 가로채 navigate(아래 components.a).
    if (/\.md$/i.test(resolved)) {
      const anchor = hash ? `#${hash}` : "";
      return `/learn?path=${encodeURIComponent(resolved)}${anchor}`;
    }

    // 그 외(이미지·첨부) → 정적 학습 자산 URL.
    return learningAssetUrl(resolved);
  };
}

export function MarkdownView({ content, dir }: { content: string; dir: string }) {
  const navigate = useNavigate();
  const urlTransform = useMemo(() => makeUrlTransform(dir), [dir]);

  return (
    <div className="markdown-body">
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSlug]}
        urlTransform={urlTransform}
        components={{
          // 내부 /learn 링크는 SPA 네비게이션으로(전체 새로고침 방지). 외부/앵커는 기본 동작.
          a({ href, children, ...rest }) {
            const isInternalLearn = typeof href === "string" && href.startsWith("/learn?");
            if (isInternalLearn) {
              return (
                <a
                  href={href}
                  onClick={(e) => {
                    e.preventDefault();
                    void navigate(href);
                  }}
                  {...rest}
                >
                  {children}
                </a>
              );
            }
            // 외부 링크는 새 탭 + 보안 rel.
            const external = typeof href === "string" && /^https?:/i.test(href);
            return (
              <a
                href={href}
                {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                {...rest}
              >
                {children}
              </a>
            );
          },
          // 이미지 다량 → lazy 로딩 강제.
          img({ ...props }) {
            return <img loading="lazy" {...props} />;
          },
        }}
      >
        {content}
      </Markdown>
    </div>
  );
}
