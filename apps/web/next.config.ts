import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@nexa/shared", "@nexa/ui"]
};

export default nextConfig;
