'use client';

import React, { createContext, useContext, useState, useMemo, useCallback, ReactNode } from 'react';
import { useAuth } from './AuthContext';

type CallStatus = 'idle' | 'connecting' | 'active' | 'ending' | 'error';

interface DialerContextType {
  status: CallStatus;
  activeProvider: { name: string; specialty: string } | null;
  startCall: (providerId: string) => Promise<void>;
  endCall: () => void;
  error: string | null;
}

const DialerContext = createContext<DialerContextType | undefined>(undefined);

export function DialerProvider({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState<CallStatus>('idle');
  const [activeProvider, setActiveProvider] = useState<{ name: string; specialty: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startCall = useCallback(async (providerId: string) => {
    if (status !== 'idle') return;
    if (!accessToken) {
      setError('You must be signed in to place a call.');
      setStatus('error');
      return;
    }

    setStatus('connecting');
    setError(null);

    try {
      // Fetch provider info + phone number from bridge endpoint
      const bridgeRes = await fetch('/api/dialer/bridge', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ providerId }),
      });

      const bridgeData = await bridgeRes.json();

      if (!bridgeRes.ok || !bridgeData.success || !bridgeData.data) {
        throw new Error(bridgeData.error || 'Failed to fetch provider info');
      }

      const { provider, destination } = bridgeData.data;
      setActiveProvider(provider);

      // Place outbound Twilio call to provider's phone
      const callRes = await fetch('/api/dialer/call', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ phoneNumber: destination.number }),
      });

      const callData = await callRes.json();

      if (!callRes.ok || !callData.success) {
        throw new Error(callData.detail || callData.error || 'Call failed');
      }

      setStatus('active');
    } catch (err: any) {
      setError(err.message || 'Call failed');
      setStatus('error');
      setActiveProvider(null);
    }
  }, [accessToken, status]);

  const endCall = useCallback(() => {
    setStatus('idle');
    setActiveProvider(null);
    setError(null);
  }, []);

  const value = useMemo(
    () => ({ status, activeProvider, startCall, endCall, error }),
    [status, activeProvider, startCall, endCall, error],
  );

  return (
    <DialerContext.Provider value={value}>
      {children}
    </DialerContext.Provider>
  );
}

export function useDialer() {
  const context = useContext(DialerContext);
  if (context === undefined) {
    throw new Error('useDialer must be used within a DialerProvider');
  }
  return context;
}
