import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Output as standalone server — prevents static prerendering of
  // error pages that crash with framer-motion + React 19 SSR
  output: "standalone",
};

export default nextConfig;
