"use client";

import "./globals.scss";
import { Theme } from "@carbon/react";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-TW">
      <head>
        <title>AI KM 知識管理平台</title>
        <meta name="description" content="AI-powered Knowledge Management Platform" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <Theme theme="g10">
          {children}
        </Theme>
      </body>
    </html>
  );
}
