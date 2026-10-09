'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { CalendarDays, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react';
import { parseApiDate } from '@/lib/date';

interface Appointment {
    id: string; start_time: string; end_time?: string;
    title?: string; notes?: string; status: string;
}

const STATUS_META: Record<string, { label: string; color: string; bg: string; icon: any }> = {
    confirmed: { label: 'Confirmed', color: '#10b981', bg: 'rgba(16,185,129,0.12)', icon: CheckCircle },
    pending:   { label: 'Pending',   color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', icon: AlertCircle },
    cancelled: { label: 'Cancelled', color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  icon: XCircle },
};

function fmtDate(d: string) {
    return parseApiDate(d).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}
function fmtTime(d: string) {
    return parseApiDate(d).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

export default function UserAppointments() {
    const { accessToken } = useAuth();
    const [appointments, setAppointments] = useState<Appointment[]>([]);
    const [loading, setLoading] = useState(true);
    const [tab, setTab] = useState<'upcoming' | 'past'>('upcoming');

    useEffect(() => {
        if (!accessToken) return;
        fetch('/api/appointments', { headers: { Authorization: `Bearer ${accessToken}` } })
            .then(r => r.json())
            .then(d => setAppointments(d?.data?.appointments || []))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [accessToken]);

    const now = Date.now();
    const upcoming = appointments.filter(a => parseApiDate(a.start_time).getTime() >= now);
    const past     = appointments.filter(a => parseApiDate(a.start_time).getTime() < now);
    const filtered = tab === 'upcoming' ? upcoming : past;

    const confirmed  = appointments.filter(a => a.status === 'confirmed').length;
    const thisMonth  = appointments.filter(a => {
        const d = parseApiDate(a.start_time);
        const now2 = new Date();
        return d.getMonth() === now2.getMonth() && d.getFullYear() === now2.getFullYear();
    }).length;

    return (
        <div style={{ maxWidth: 800 }}>
            {/* Header */}
            <div style={{ marginBottom: 24 }}>
                <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: '-0.02em' }}>My Appointments</h1>
                <p style={{ color: 'var(--text-4)', marginTop: 4, fontSize: 13, margin: '4px 0 0' }}>Your scheduled meetings and consultations</p>
            </div>

            {/* Summary cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14, marginBottom: 24 }}>
                {[
                    { label: 'Total',      value: appointments.length, color: '#6366f1', icon: CalendarDays },
                    { label: 'Upcoming',   value: upcoming.length,     color: '#d4a94f', icon: Clock },
                    { label: 'Confirmed',  value: confirmed,           color: '#10b981', icon: CheckCircle },
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

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
                {(['upcoming', 'past'] as const).map(t => (
                    <button key={t} onClick={() => setTab(t)} style={{
                        padding: '7px 18px', borderRadius: 9, fontSize: 13, fontWeight: 700,
                        border: tab === t ? 'none' : '1px solid var(--border-default)',
                        background: tab === t
                            ? 'linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%)'
                            : 'var(--bg-card)',
                        color: tab === t ? '#fff' : 'var(--text-2)',
                        cursor: 'pointer', textTransform: 'capitalize',
                        boxShadow: tab === t ? '0 3px 10px rgba(185, 134, 42,0.25)' : 'none',
                        transition: 'all 0.15s',
                    }}>
                        {t === 'upcoming' ? `Upcoming (${upcoming.length})` : `Past (${past.length})`}
                    </button>
                ))}
            </div>

            {/* Appointment cards */}
            {loading ? (
                <div style={{ color: 'var(--text-4)', fontSize: 13, padding: '40px 0', textAlign: 'center' }}>Loading...</div>
            ) : filtered.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text-4)' }}>
                    <CalendarDays size={44} style={{ opacity: 0.2, marginBottom: 14 }} />
                    <p style={{ fontSize: 14, margin: 0 }}>No {tab} appointments.</p>
                    <p style={{ fontSize: 12, marginTop: 6, opacity: 0.7 }}>Your AI agent will book appointments automatically when leads are ready.</p>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {filtered.map(a => {
                        const meta = STATUS_META[a.status] || STATUS_META.pending;
                        const Icon = meta.icon;
                        const dt = parseApiDate(a.start_time);
                        const isPast = dt.getTime() < now;
                        return (
                            <div key={a.id} style={{
                                background: 'var(--bg-card)', border: '1px solid var(--border-default)',
                                borderRadius: 14, padding: '18px 22px',
                                display: 'flex', alignItems: 'center', gap: 18,
                                opacity: isPast ? 0.7 : 1,
                            }}>
                                {/* Date block */}
                                <div style={{
                                    flexShrink: 0, width: 52, height: 56,
                                    borderRadius: 12, background: `${meta.color}12`,
                                    border: `1px solid ${meta.color}22`,
                                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <div style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', color: meta.color, letterSpacing: '0.05em' }}>
                                        {dt.toLocaleDateString('en-US', { month: 'short' })}
                                    </div>
                                    <div style={{ fontSize: 24, fontWeight: 800, lineHeight: 1, color: 'var(--text-1)' }}>{dt.getDate()}</div>
                                </div>

                                {/* Info */}
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>
                                        {a.title || a.notes || 'Appointment'}
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: 'var(--text-4)' }}>
                                        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                            <CalendarDays size={11} />
                                            {fmtDate(a.start_time)}
                                        </span>
                                        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                            <Clock size={11} />
                                            {fmtTime(a.start_time)}
                                            {a.end_time && ` – ${fmtTime(a.end_time)}`}
                                        </span>
                                    </div>
                                </div>

                                {/* Status badge */}
                                <span style={{
                                    display: 'flex', alignItems: 'center', gap: 5,
                                    padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                                    background: meta.bg, color: meta.color, flexShrink: 0,
                                }}>
                                    <Icon size={11} />
                                    {meta.label}
                                </span>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
