import type { NextConfig } from "next";

// Set in the single-image build: the browser calls /api and Next forwards it to the API.
const internalApi = process.env.CHARIE_INTERNAL_API_URL;

const nextConfig: NextConfig = {
  // Self-contained server bundle for the container image — no node_modules copy.
  output: "standalone",
  reactStrictMode: true,
  // The floating dev badge sits over the sidebar's account card.
  devIndicators: false,
  // Run traces stream for as long as a run lasts; the 30-second default would cut them.
  experimental: { proxyTimeout: 15 * 60 * 1000 },
  async rewrites() {
    return internalApi ? [{ source: "/api/:path*", destination: `${internalApi}/:path*` }] : [];
  },
};

export default nextConfig;
