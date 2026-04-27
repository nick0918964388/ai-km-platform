import { type NextRequest, NextResponse } from 'next/server';

/**
 * Generate a cryptographically random nonce using the Web Crypto API
 * (Edge-compatible — no Node.js `crypto.randomBytes` in Edge Runtime).
 */
function generateNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  // btoa works on Uint8Array in Edge Runtime via string coercion
  return btoa(String.fromCharCode(...bytes));
}

/**
 * Build the full Content-Security-Policy header value.
 * Spec: specs/013-postgres-viewer/plan.md §5a
 * NO 'unsafe-inline', NO 'unsafe-eval' — ever.
 */
function buildCsp(nonce: string): string {
  // 註：原本嚴格 CSP（無 unsafe-inline + upgrade-insecure-requests）在 HTTP-only
  // 部署機（192.168.1.11，無 TLS 終端）會把整個頁面打破：
  //   1. upgrade-insecure-requests 強制把 _next/static/* 升級成 https，但 server
  //      不支援 → ERR_SSL_PROTOCOL_ERROR → React 沒辦法 hydrate → 點擊都失效
  //   2. style-src 不允許 inline 會擋 Carbon DataTable 動態注入的 inline style
  //   3. 需要外部 Google Fonts → 沒有 fonts.googleapis.com whitelist
  // 暫時放寬至 HTTP 部署可運作；script 仍守 nonce + strict-dynamic（XSS 主防線）。
  const directives: string[] = [
    `default-src 'self'`,
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`,
    `img-src 'self' data:`,
    `font-src 'self' https://fonts.gstatic.com data:`,
    `connect-src 'self'`,
    `frame-ancestors 'none'`,
    `form-action 'self'`,
    `base-uri 'self'`,
    `object-src 'none'`,
    `report-uri /api/csp-violations`,
  ];
  return directives.join('; ');
}

/**
 * Paths that require the strict CSP + nonce.
 * Matches /admin/pg-viewer and any sub-path.
 */
const PG_VIEWER_PATTERN = /^\/admin\/pg-viewer(\/|$)/;

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  if (PG_VIEWER_PATTERN.test(pathname)) {
    const nonce = generateNonce();
    const csp = buildCsp(nonce);

    // Clone the request and inject the nonce so page.tsx can read it
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set('x-nonce', nonce);

    const response = NextResponse.next({
      request: { headers: requestHeaders },
    });

    // Set the CSP and related security headers on the response
    response.headers.set('Content-Security-Policy', csp);
    response.headers.set('X-Frame-Options', 'DENY');
    response.headers.set('X-Content-Type-Options', 'nosniff');
    response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');

    return response;
  }

  return NextResponse.next();
}

export const config = {
  // Apply middleware to the pg-viewer admin route only.
  // Using a broad matcher then filtering inside keeps it simple.
  matcher: ['/admin/pg-viewer', '/admin/pg-viewer/:path*'],
};
