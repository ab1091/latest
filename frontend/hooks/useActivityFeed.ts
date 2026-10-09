'use client';

import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';

export interface ActivityFeedEvent {
    id: string;
    business_id: string;
    lead_id: string | null;
    event_type: string;
    title: string;
    metadata: Record<string, any>;
    created_at: string;
}

const MAX_EVENTS = 100;

/**
 * Live activity feed via SSE. The native EventSource API can't send an
 * Authorization header, so the token is passed as a query param on the
 * stream URL only — every other request in this app still uses the header.
 */
export function useActivityFeed() {
    const { accessToken } = useAuth();
    const [events, setEvents] = useState<ActivityFeedEvent[]>([]);
    const [connected, setConnected] = useState(false);
    const sourceRef = useRef<EventSource | null>(null);

    useEffect(() => {
        if (!accessToken) return;

        fetch(`/api/activity-feed?limit=${MAX_EVENTS}`, {
            headers: { Authorization: `Bearer ${accessToken}` },
        })
            .then(r => r.json())
            .then(data => {
                if (data?.success) setEvents(data.data.events);
            })
            .catch(() => {});

        const source = new EventSource(`/api/activity-feed/stream?token=${encodeURIComponent(accessToken)}`);
        sourceRef.current = source;

        source.addEventListener('connected', () => setConnected(true));
        source.onerror = () => setConnected(false);
        source.onmessage = (e) => {
            try {
                const event: ActivityFeedEvent = JSON.parse(e.data);
                setEvents(prev => [event, ...prev].slice(0, MAX_EVENTS));
            } catch {}
        };

        return () => {
            source.close();
            sourceRef.current = null;
            setConnected(false);
        };
    }, [accessToken]);

    return { events, connected };
}
