import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker 배포용 — .next/standalone 에 자체 실행 서버 생성 (frontend/Dockerfile 이 사용)
  output: "standalone",
};

export default nextConfig;
