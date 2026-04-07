import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
