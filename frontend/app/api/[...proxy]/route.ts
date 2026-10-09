import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

async function handler(request: NextRequest, { params }: { params: { proxy: string[] } }) {
    const path = params.proxy.join('/');
    const search = request.nextUrl.search;
    const url = `${BACKEND}/api/${path}${search}`;

    const headers = new Headers(request.headers);
    headers.set('ngrok-skip-browser-warning', '1');
    headers.delete('host');

    // super_admin agency drill-down: the browser can't attach a custom header
    // to every one of the dozens of existing fetch() call sites across the
    // app, so the selected agency travels as a cookie instead and gets
    // translated into the X-Business-Id header the backends already expect.
    if (!headers.has('x-business-id')) {
        const selected = request.cookies.get('sa_business_id')?.value;
        if (selected) headers.set('X-Business-Id', selected);
    }

    const body = request.method !== 'GET' && request.method !== 'HEAD'
        ? await request.arrayBuffer()
        : undefined;

    const res = await fetch(url, {
        method: request.method,
        headers,
        body: body ? Buffer.from(body) : undefined,
    });

    const resHeaders = new Headers(res.headers);
    resHeaders.delete('content-encoding');

    return new NextResponse(res.body, {
        status: res.status,
        headers: resHeaders,
    });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
