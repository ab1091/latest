'use client';

// useCallStatus — Tayyba's frontend hook
// Fetches voice call status for a given appointment from the backend.

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';

export type CallOutcome =
    | 'confirmed'
    | 'cancelled'
    | 'reschedule_requested'
    | 'no_answer'
    | 'voicemail'
    | 'failed';

export interface CallStatusData {
    callId: string;
    outcome: CallOutcome | null;
    summary: string | null;
    transcript: string | null;
    durationSeconds: number | null;
    status: string;
    createdAt: string;
}


export function useCallStatus(appointmentId: string | null) {
    const { accessToken } = useAuth();
    const [callStatus, setCallStatus] = useState<CallStatusData | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchCallStatus = useCallback(async () => {
        if (!appointmentId || !accessToken) return;

        setIsLoading(true);
        setError(null);

        try {
            const response = await fetch(
                `/api/appointments/${appointmentId}/call-status`,
                {
                    headers: { Authorization: `Bearer ${accessToken}` },
                }
            );

            if (response.status === 404) {
                // No call record yet — not an error
                setCallStatus(null);
                return;
            }

            if (!response.ok) {
                throw new Error('Failed to fetch call status');
            }

            const data = await response.json();
            setCallStatus(data.data ?? null);
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setIsLoading(false);
        }
    }, [appointmentId, accessToken]);

    useEffect(() => {
        fetchCallStatus();
    }, [fetchCallStatus]);

    return { callStatus, isLoading, error, refetch: fetchCallStatus };
}
