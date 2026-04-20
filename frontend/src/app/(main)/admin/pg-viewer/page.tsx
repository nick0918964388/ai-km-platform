/**
 * /admin/pg-viewer — PostgreSQL Viewer
 *
 * Server Component: reads nonce from request headers (injected by middleware).
 * Admin-only: non-admin users are redirected to / with a 403-equivalent message.
 * Feature flag: NEXT_PUBLIC_PG_VIEWER_ENABLED=false → renders disabled banner (SSR).
 * Backend 404 on /api/pg-viewer/tables → also renders disabled banner (client-side).
 */
import { headers } from 'next/headers';
import PgViewerClient from './PgViewerClient';

export const dynamic = 'force-dynamic';

export default async function PgViewerPage() {
  // Read the nonce that middleware injected into request headers.
  // This is a Server Component so headers() is available.
  const headersList = await headers();
  const nonce = headersList.get('x-nonce') ?? '';

  // SSR feature-flag check — evaluated on the server, no client round-trip.
  const featureEnabled = process.env.NEXT_PUBLIC_PG_VIEWER_ENABLED !== 'false';

  return (
    <PgViewerClient
      nonce={nonce}
      featureEnabled={featureEnabled}
    />
  );
}
