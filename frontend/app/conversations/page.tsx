'use client';

import { Suspense } from 'react';
import { ConversationsInner } from '@/components/panels/ConversationsPanel';

export default function ConversationsPage() {
    return (
        <Suspense>
            <ConversationsInner />
        </Suspense>
    );
}
