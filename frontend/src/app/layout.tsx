import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '車輛維修知識庫 - AI 智慧助理',
  description: 'AI 驅動的車輛維修知識管理平台',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
