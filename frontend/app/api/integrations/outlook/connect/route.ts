import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

// ai-service's /outlook/connect issues a 302 to Microsoft's login page. The
// generic [...proxy] route follows redirects server-side and returns the
// final body instead of a real redirect, which breaks OAuth (wrong address
// bar, wrong redirect_uri context) — so this one needs its own handler that
// forwards the Location header as an actual browser redirect.
export async function GET(request: NextRequest) {
    const token = request.nextUrl.searchParams.get('token') || '';
    const res = await fetch(
        `${BACKEND}/api/integrations/outlook/connect?token=${encodeURIComponent(token)}`,
        { redirect: 'manual' }
    );

    const location = res.headers.get('location');
    if (!location) {
        return NextResponse.json({ error: 'Failed to start Outlook connection' }, { status: res.status || 502 });
    }

    return NextResponse.redirect(location);
}
