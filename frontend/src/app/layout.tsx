import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Agent Grid — MCP 신뢰성 레지스트리",
    template: "%s | Agent Grid",
  },
  description:
    "AI 에이전트/MCP 서버의 시스템 신뢰성(예외 처리·타임아웃·재시도 등)을 정적 분석으로 평가해 A~F 등급과 산출 근거를 공개하는 개발자 레지스트리",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-lg font-bold tracking-tight">Agent Grid</span>
              <span className="hidden text-xs text-zinc-500 sm:inline dark:text-zinc-400">
                MCP 서버 신뢰성 레지스트리
              </span>
            </Link>
            <nav className="flex gap-1 text-sm font-medium">
              <Link
                href="/"
                className="rounded-md px-3 py-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                디렉토리
              </Link>
              <Link
                href="/submit"
                className="rounded-md px-3 py-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                제출
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
          {children}
        </main>
        <footer className="border-t border-zinc-200 dark:border-zinc-800">
          <div className="mx-auto w-full max-w-6xl px-4 py-4 text-xs text-zinc-500 dark:text-zinc-400">
            모든 등급은 정적 자동 분석 결과이며 실제 운영 품질을 보장하지 않습니다 —
            상세 페이지에 분석 일시·버전 병기
          </div>
        </footer>
      </body>
    </html>
  );
}
