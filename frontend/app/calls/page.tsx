'use client';

import { Suspense } from 'react';
import { CallsPanel } from '@/components/panels/CallsPanel';

export default function CallsPage() {
    return (
        <Suspense>
            <CallsPanel />
        </Suspense>
    );
}
