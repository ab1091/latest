'use client';

import React from 'react';
import { PhoneOff, User, Loader2, AlertCircle } from 'lucide-react';
import { useDialer } from '@/contexts/DialerContext';

const LEVELS = [10, 18, 14, 22, 12, 16];

export function DialerWidget() {
  const { status, activeProvider, endCall, error } = useDialer();

  if (status === 'idle' && !error) return null;

  return (
    <div className="fixed bottom-8 right-8 z-[9999] animate-fade-in">
      <div className="glass-panel w-80 p-6 shadow-2xl" style={{ borderColor: 'rgba(212, 169, 79, 0.24)' }}>
        <div className="flex flex-col gap-4 text-center">
          
          {error ? (
            <>
              <div className="flex justify-center">
                <div className="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center text-red-500">
                  <AlertCircle size={24} />
                </div>
              </div>
              <div>
                <h4 className="text-red-400 font-bold uppercase text-xs tracking-wider">Connection Error</h4>
                <p className="mt-1 text-sm" style={{ color: 'var(--text-3)' }}>{error}</p>
              </div>
              <button 
                onClick={endCall}
                className="btn btn-secondary w-full py-2"
              >
                Dismiss
              </button>
            </>
          ) : (
            <>
              <div className="flex justify-center items-center gap-4">
                <div
                  className={`relative flex h-16 w-16 items-center justify-center rounded-3xl ${status === 'active' ? 'animate-pulse' : ''}`}
                  style={{ background: 'rgba(212, 169, 79, 0.12)', color: 'var(--primary)' }}
                >
                  <User size={32} />
                  {status === 'active' && (
                    <div className="absolute -top-1 -right-1 h-4 w-4 rounded-full border-2 animate-pulse" style={{ background: 'var(--status-success)', borderColor: 'var(--bg-root)' }} />
                  )}
                </div>
              </div>

              <div>
                <h3 className="text-lg font-bold gradient-text">{activeProvider?.name || 'Call Initialization'}</h3>
                <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--primary-text)' }}>{activeProvider?.specialty || 'Voice Bridge'}</p>
              </div>

              <div className="py-2 flex flex-col items-center gap-2">
                {status === 'connecting' && (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" style={{ color: 'var(--primary)' }} />
                    <span className="text-xs font-medium animate-pulse" style={{ color: 'var(--primary-text)' }}>Requesting Bridge...</span>
                  </>
                )}
                {status === 'active' && (
                  <>
                    <div className="flex gap-1 h-6 items-center">
                      {LEVELS.map((height, i) => (
                        <div 
                          key={i} 
                          className="w-1 rounded-full animate-[bounce_0.6s_infinite]" 
                          style={{ 
                            height: `${height}px`,
                            background: 'var(--primary)',
                            animationDelay: `${i * 0.1}s` 
                          }} 
                        />
                      ))}
                    </div>
                    <span className="text-xs font-bold uppercase tracking-widest" style={{ color: 'var(--status-success)' }}>Live PSTN Connection</span>
                  </>
                )}
              </div>

              <button 
                onClick={endCall}
                className="flex w-full items-center justify-center gap-2 rounded-xl py-3 font-bold text-[#2c0f0f] transition-all"
                style={{ background: 'linear-gradient(180deg, #ff8f8f 0%, #f46d6d 100%)', boxShadow: '0 12px 24px rgba(255, 143, 143, 0.18)' }}
              >
                <PhoneOff size={18} />
                END SESSION
              </button>
            </>
          )}

        </div>
      </div>
    </div>
  );
}
