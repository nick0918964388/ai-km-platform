/**
 * /admin/pg-viewer/query — PostgreSQL SQL Editor
 *
 * Server Component: reads nonce from request headers (injected by middleware).
 * The middleware matcher already covers /admin/pg-viewer/:path*, so this route
 * automatically receives nonce-based CSP — no additional middleware changes needed.
 *
 * Admin-only: client component enforces redirect on non-admin users.
 * Feature flag: NEXT_PUBLIC_PG_VIEWER_ENABLED=false → client renders disabled banner.
 */

import { headers } from 'next/headers';
import SqlEditorClient from './SqlEditorClient';

export const dynamic = 'force-dynamic';

export default async function SqlEditorPage() {
  // Read the nonce that middleware injected into request headers.
  // This is a Server Component so headers() is available.
  const headersList = await headers();
  const nonce = headersList.get('x-nonce') ?? '';

  // SSR feature-flag check — evaluated on the server, no client round-trip.
  const featureEnabled = process.env.NEXT_PUBLIC_PG_VIEWER_ENABLED !== 'false';

  // nonce is available for future use (e.g. inline script injection via dangerouslySetInnerHTML)
  // Currently unused in this page as all scripts are external bundles with nonce set by Next.js.
  void nonce;

  return (
    <SqlEditorClient
      featureEnabled={featureEnabled}
    />
  );
}
