'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Phone, Clock, CheckCircle, XCircle, VoicemailIcon, PhoneMissed } from 'lucide-react';
import { parseApiDate } from '@/lib/date';

interface Call {
    id: string; callId: string; phone?: string;
    outcome?: string; durationSeconds?: number;
    createdAt: string; summary?: string; patientName?: string;
}


const OUTCOME_META: Record<string, { label: string; color: string; bg: string; icon: any }> = {
    'Confirmed':           { label: 'Confirmed',   color: '#10b981', bg: 'rgba(16,185,129,0.12)',  icon: CheckCircle },
    'Voicemail':           { label: 'Voicemail',   color: '#8b5cf6', bg: 'rgba(139,92,246,0.12)',  icon: VoicemailIcon },
    'No Answer':           { label: 'No Answer',   color: '#f59e0b', bg: 'rgba(245,158,11,0.12)',  icon: PhoneMissed },
    'Failed':              { label: 'Failed',       color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  icon: XCircle },
    'Cancelled':           { label: 'Cancelled',   color: '#6b7280', bg: 'rgba(107,114,128,0.1)', icon: XCircle },
    'Reschedule Requested':{ label: 'Rescheduled', color: '#6366f1', bg: 'rgba(99,102,241,0.12)', icon: Phone },
    'Information':         { label: 'Info Call',   color: '#d4a94f', bg: 'rgba(212, 169, 79,0.12)', icon: Phone },
};

function fmtDuration(s?: number) {
    if (!s) return '—';
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

function fmtDate(d: string) {
    return parseApiDate(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function fmtTime(d: string) {
    return parseApiDate(d).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

export default function UserCalls() {
    const { accessToken } = useAuth();
    const [calls, setCalls] = useState<Call[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState<string>('all');

    useEffect(() => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };

        // Get user's leads first to filter calls by their phone numbers
        fetch(`/api/leads`, { headers: h })
            .then(r => r.json())
            .then(async leadsRes => {
                const myLeads = leadsRes?.data?.leads || [];
                const myPhones = new Set(myLeads.map((l: any) => l.phone).filter(Boolean));

                const callsRes = await fetch('/api/crm/calls', { headers: h }).then(r => r.json());
                const allCalls: Call[] = callsRes?.data?.calls || [];
                setCalls(allCalls.filter((c: Call) => myPhones.has(c.phone)));
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [accessToken]);

    const outcomes = ['all', ...Array.from(new Set(calls.map(c => c.outcome || 'Unknown')))];
    const filtered = filter === 'all' ? calls : calls.filter(c => (c.outcome || 'Unknown') === filter);

    const totalDuration = calls.reduce((sum, c) => sum + (c.durationSeconds || 0), 0);
    const confirmed = calls.filter(c => c.outcome === 'Confirmed').length;

    return (
        <div style={{ maxWidth: 900 }}>
            {/* Header */}
            <div style={{ marginBottom: 24 }}>
                <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: '-0.02em' }}>Call History</h1>
                <p style={{ color: 'var(--text-4)', marginTop: 4, fontSize: 13, margin: '4px 0 0' }}>All calls associated with your leads</p>
            </div>

            {/* Summary cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14, marginBottom: 24 }}>
                {[
                    { label: 'Total Calls',   value: calls.length,                   color: '#6366f1', icon: Phone },
                    { label: 'Confirmed',     value: confirmed,                      color: '#10b981', icon: CheckCircle },
                    { label: 'Total Duration',value: fmtDuration(totalDuration),     color: '#f59e0b', icon: Clock },
                ].map(s => {
                    const Icon = s.icon;
                    return (
                        <div key={s.label} style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 13, padding: '18px 20px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 10 }}>
                                <div style={{ width: 32, height: 32, borderRadius: 9, background: `${s.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <Icon size={15} color={s.color} />
                                </div>
                                <span style={{ fontSize: 12, color: 'var(--text-4)', fontWeight: 600 }}>{s.label}</span>
                            </div>
                            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-1)' }}>{loading ? '—' : s.value}</div>
                        </div>
                    );
                })}
            </div>

            {/* Filter tabs */}
            {!loading && calls.length > 0 && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
                    {outcomes.map(o => (
                        <button key={o} onClick={() => setFilter(o)} style={{
                            padding: '5px 14px', borderRadius: 8, border: '1px solid var(--border-default)',
                            background: filter === o ? 'var(--primary)' : 'var(--bg-card)',
                            color: filter === o ? '#fff' : 'var(--text-2)',
                            cursor: 'pointer', fontSize: 12, fontWeight: 600, textTransform: 'capitalize',
                            transition: 'all 0.15s',
                        }}>{o === 'all' ? `All (${calls.length})` : o.replace('_', ' ')}</button>
                    ))}
                </div>
            )}

            {/* Calls list */}
            {loading ? (
                <div style={{ color: 'var(--text-4)', fontSize: 13, padding: '40px 0', textAlign: 'center' }}>Loading...</div>
            ) : filtered.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-4)' }}>
                    <Phone size={44} style={{ opacity: 0.2, marginBottom: 14 }} />
                    <p style={{ fontSize: 14, margin: 0 }}>No calls yet.</p>
                    <p style={{ fontSize: 12, marginTop: 6, opacity: 0.7 }}>Calls will appear here once your AI agent starts making calls to your leads.</p>
                </div>
            ) : (
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                    {filtered.map((call, i) => {
                        const meta = OUTCOME_META[call.outcome || ''] || { label: call.outcome || 'Unknown', color: '#6b7280', bg: 'rgba(107,114,128,0.1)', icon: Phone };
                        const Icon = meta.icon;
                        return (
                            <div key={call.id} style={{
                                padding: '14px 20px',
                                borderBottom: i < filtered.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                                display: 'flex', alignItems: 'center', gap: 14,
                            }}>
                                {/* Outcome icon */}
                                <div style={{ width: 38, height: 38, borderRadius: 11, background: meta.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                    <Icon size={16} color={meta.color} />
                                </div>

                                {/* Phone + name */}
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontWeight: 700, fontSize: 13 }}>{call.patientName || call.phone || 'Unknown'}</div>
                                    <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 1 }}>
                                        {call.phone || '—'}
                                    </div>
                                </div>

                                {/* Duration */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text-4)', flexShrink: 0 }}>
                                    <Clock size={12} />
                                    {fmtDuration(call.durationSeconds)}
                                </div>

                                {/* Date */}
                                <div style={{ fontSize: 11, color: 'var(--text-4)', flexShrink: 0, textAlign: 'right' }}>
                                    <div>{call.createdAt ? fmtDate(call.createdAt) : '—'}</div>
                                    <div>{call.createdAt ? fmtTime(call.createdAt) : ''}</div>
                                </div>

                                {/* Outcome badge */}
                                <span style={{
                                    padding: '3px 10px', borderRadius: 20, fontSize: 10, fontWeight: 700,
                                    background: meta.bg, color: meta.color, flexShrink: 0,
                                }}>{meta.label}</span>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
