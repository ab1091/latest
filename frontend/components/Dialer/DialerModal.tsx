'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { Phone, PhoneOff, Delete, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import styles from './DialerModal.module.css';

const KEYS = [
  ['1', ''],
  ['2', 'ABC'],
  ['3', 'DEF'],
  ['4', 'GHI'],
  ['5', 'JKL'],
  ['6', 'MNO'],
  ['7', 'PQRS'],
  ['8', 'TUV'],
  ['9', 'WXYZ'],
  ['*', ''],
  ['0', '+'],
  ['#', ''],
];

type CallState = 'idle' | 'calling' | 'success' | 'error';

interface DialerModalProps {
  onClose: () => void;
}

export function DialerModal({ onClose }: DialerModalProps) {
  const { accessToken } = useAuth();
  const [digits, setDigits] = useState('');
  const [callState, setCallState] = useState<CallState>('idle');
  const [callSid, setCallSid] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const press = useCallback((digit: string) => {
    setDigits(d => {
      // Long-press 0 convention: first key press on empty field with '0' → '+'
      if (digit === '0' && d === '') return '+';
      return (d + digit).slice(0, 15);
    });
  }, []);

  const del = useCallback(() => {
    setDigits(d => d.slice(0, -1));
  }, []);

  const reset = useCallback(() => {
    setCallState('idle');
    setDigits('');
    setCallSid('');
    setErrorMsg('');
  }, []);

  const dial = useCallback(async () => {
    if (!digits || callState !== 'idle') return;

    const raw = digits.replace(/\D/g, '');
    const phoneNumber = digits.startsWith('+') ? digits : raw.length > 10 ? `+${raw}` : `+1${raw}`;
    const token = accessToken || localStorage.getItem('accessToken') || '';

    setCallState('calling');
    setErrorMsg('');

    try {
      const res = await fetch('/api/dialer/call', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ phoneNumber }),
      });

      const data = await res.json();

      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Call failed');
      }

      setCallSid(data.callSid || '');
      setCallState('success');
    } catch (err: any) {
      setErrorMsg(err.message || 'Unknown error');
      setCallState('error');
    }
  }, [digits, callState, accessToken]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return; }
      if (/^[0-9*#+]$/.test(e.key)) { setDigits(d => (d + e.key).slice(0, 15)); return; }
      if (e.key === 'Backspace') { setDigits(d => d.slice(0, -1)); return; }
      if (e.key === 'Enter') { void dial(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [digits, callState, dial, onClose]);

  const formattedDisplay = (() => {
    const raw = digits.replace(/\D/g, '');
    if (digits.startsWith('+')) return digits;
    if (raw.length <= 3) return raw;
    if (raw.length <= 6) return `(${raw.slice(0, 3)}) ${raw.slice(3)}`;
    if (raw.length <= 10) return `(${raw.slice(0, 3)}) ${raw.slice(3, 6)}-${raw.slice(6)}`;
    return `+1 (${raw.slice(0, 3)}) ${raw.slice(3, 6)}-${raw.slice(6, 10)}`;
  })();

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>

        <div className={styles.header}>
          <span className={styles.headerTitle}>Dial</span>
          <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {/* Number display */}
        <div className={styles.displayWrap}>
          <input
            ref={inputRef}
            readOnly
            className={styles.display}
            value={formattedDisplay || ''}
            placeholder="Enter number"
            aria-label="Phone number"
          />
          {digits && (
            <button type="button" className={styles.deleteBtn} onClick={del} aria-label="Delete">
              <Delete size={16} />
            </button>
          )}
        </div>

        {/* Keypad */}
        <div className={styles.keypad}>
          {KEYS.map(([digit, sub]) => (
            <button
              key={digit}
              type="button"
              className={styles.key}
              onClick={() => press(digit)}
              disabled={callState !== 'idle'}
            >
              <span className={styles.keyDigit}>{digit}</span>
              {sub && <span className={styles.keySub}>{sub}</span>}
            </button>
          ))}
        </div>

        {/* Status / Call button */}
        {callState === 'idle' && (
          <button
            type="button"
            className={styles.callBtn}
            onClick={dial}
            disabled={!digits}
            aria-label="Call"
          >
            <Phone size={22} />
          </button>
        )}

        {callState === 'calling' && (
          <div className={styles.statusRow}>
            <Loader2 size={18} className={styles.spinner} />
            <span className={styles.statusText}>Placing call…</span>
          </div>
        )}

        {callState === 'success' && (
          <div className={styles.statusSuccess}>
            <CheckCircle size={18} />
            <div>
              <div className={styles.statusText}>Call placed to {formattedDisplay}</div>
              {callSid && <div className={styles.callSid}>SID: {callSid}</div>}
            </div>
            <button type="button" className={styles.anotherBtn} onClick={reset}>New call</button>
          </div>
        )}

        {callState === 'error' && (
          <div className={styles.statusError}>
            <AlertCircle size={18} />
            <div className={styles.statusText}>{errorMsg}</div>
            <button type="button" className={styles.anotherBtn} onClick={reset}>Retry</button>
          </div>
        )}

      </div>
    </div>
  );
}
