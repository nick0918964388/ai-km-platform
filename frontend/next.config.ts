import type { NextConfig } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_URL}/api/:path*`,
      },
    ];
  },
  // REMOVED: standalone output causes navigation issues in Next.js 16
  // output: "standalone",

  // Hide Next.js dev indicators (the "N" icon in bottom-left)
  devIndicators: false,

  // Temporarily ignore TypeScript errors during build
  typescript: {
    ignoreBuildErrors: true,
  },

  // Configure images if needed
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
      },
    ],
  },
};

export default nextConfig;
