import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the container image — no node_modules copy.
  output: "standalone",
  reactStrictMode: true,
  // The floating dev badge sits over the sidebar's account card.
  devIndicators: false,
};

export default nextConfig;
