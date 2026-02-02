import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable standalone output for Docker
  output: "standalone",
  
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
