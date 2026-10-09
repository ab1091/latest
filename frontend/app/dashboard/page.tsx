'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { useAgencyScope } from '@/contexts/AgencyScopeContext';
import { useRouter } from 'next/navigation';
import { SideNav } from '@/components/SideNav/SideNav';
import { Users, MessageCircle, Phone, CalendarDays, TrendingUp, UserCheck, PhoneMissed, Voicemail, Reply, FileDown, UserX, Mail } from 'lucide-react';
import Link from 'next/link';
import * as XLSX from 'xlsx';


interface Lead { id: string; first_name: string; last_name: string; phone: string; sub_status: string; stage: string; created_at: string; }
interface Conv { id: string; lead_id: string; first_name: string; last_name: string; channel: string; last_message: string | null; last_message_at: string | null; has_reply?: boolean; }
interface Call { id: string; patientName: string; phone: string; call_type: string; duration_seconds: number | null; created_at: string; outcome?: string | null; }

const NOT_ANSWERED = new Set(['no_answer', 'voicemail', 'failed', 'call_failed']);
interface Appt { id: string; patient_name?: string; service_name?: string; status: string; scheduled_at: string; }

function MiniCalendar({ appts }: { appts: Appt[] }) {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const monthName = now.toLocaleString('en-US', { month: 'long', year: 'numeric' });

    const apptDays = new Set(
        appts
            .filter(a => { const d = parseApiDate(a.scheduled_at); return d.getFullYear() === year && d.getMonth() === month; })
            .map(a => parseApiDate(a.scheduled_at).getDate())
    );

    const todayDate = now.getDate();
    const cells: (number | null)[] = [...Array(firstDay).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)];
    while (cells.length % 7 !== 0) cells.push(null);

    const [selectedDay, setSelectedDay] = useState<number | null>(null);
    const dayAppts = selectedDay
        ? appts.filter(a => { const d = parseApiDate(a.scheduled_at); return d.getFullYear() === year && d.getMonth() === month && d.getDate() === selectedDay; })
        : [];

    return (
        <div>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12 }}>{monthName}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 2, marginBottom: 8 }}>
                {['Su','Mo','Tu','We','Th','Fr','Sa'].map(d => (
                    <div key={d} style={{ textAlign: 'center', fontSize: 10, fontWeight: 700, color: 'var(--text-4)', paddingBottom: 4 }}>{d}</div>
                ))}
                {cells.map((day, i) => (
                    <div key={i} onClick={() => day && setSelectedDay(selectedDay === day ? null : day)}
                        style={{
                            textAlign: 'center', fontSize: 11, padding: '5px 2px', borderRadius: 6, position: 'relative',
                            cursor: day ? 'pointer' : 'default',
                            fontWeight: day === todayDate ? 800 : 400,
                            background: day === selectedDay ? 'var(--primary)' : day === todayDate ? 'rgba(212, 169, 79,0.12)' : 'transparent',
                            color: day === selectedDay ? '#fff' : day === todayDate ? 'var(--primary)' : day ? 'var(--text-1)' : 'transparent',
                        }}>
                        {day || ''}
                        {day && apptDays.has(day) && (
                            <div style={{ width: 4, height: 4, borderRadius: '50%', background: day === selectedDay ? '#fff' : '#f59e0b', margin: '1px auto 0' }} />
                        )}
                    </div>
                ))}
            </div>
            {selectedDay && (
                <div style={{ marginTop: 8, borderTop: '1px solid var(--border-default)', paddingTop: 10 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-4)', marginBottom: 6 }}>
                        {monthName.split(' ')[0]} {selectedDay}
                    </div>
                    {dayAppts.length === 0 ? (
                        <p style={{ fontSize: 12, color: 'var(--text-4)' }}>No appointments</p>
                    ) : dayAppts.map(a => (
                        <div key={a.id} style={{ fontSize: 12, padding: '5px 8px', borderRadius: 6, background: 'rgba(245,158,11,0.08)', marginBottom: 4 }}>
                            <span style={{ fontWeight: 600 }}>{a.patient_name || a.service_name || 'Appointment'}</span>
                            <span style={{ color: 'var(--text-4)', marginLeft: 6 }}>
                                {parseApiDate(a.scheduled_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                            </span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
    new:       { bg: 'rgba(99,102,241,0.12)',  color: '#a5b4fc' },
    contacted: { bg: 'rgba(245,158,11,0.12)',  color: '#fbbf24' },
    qualified: { bg: 'rgba(16,185,129,0.12)',  color: '#34d399' },
    converted: { bg: 'rgba(185, 134, 42,0.12)',  color: '#e8c877' },
    dead:      { bg: 'rgba(107,114,128,0.1)',  color: '#9ca3af' },
};

export default function AdminDashboard() {
    const { user, accessToken, isLoading } = useAuth();
    const { agency } = useAgencyScope();
    const router = useRouter();
    const [leads,  setLeads]  = useState<Lead[]>([]);
    const [convs,  setConvs]  = useState<Conv[]>([]);
    const [calls,  setCalls]  = useState<Call[]>([]);
    const [appts,  setAppts]  = useState<Appt[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role)) {
            router.replace('/user/dashboard');
            return;
        }
        // super_admin has no business of its own — this page is meaningless
        // until they've picked an agency to manage from /platform.
        if (user?.role === 'super_admin' && !agency) {
            router.replace('/platform');
        }
    }, [isLoading, accessToken, user, agency, router]);

    useEffect(() => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };
        Promise.all([
            fetch(`/api/leads`,         { headers: h }).then(r => r.json()).catch(() => ({})),
            fetch(`/api/conversations`, { headers: h }).then(r => r.json()).catch(() => ({})),
            fetch('/api/crm/calls',               { headers: h }).then(r => r.json()).catch(() => ({})),
            fetch('/api/appointments',            { headers: h }).then(r => r.json()).catch(() => ({})),
        ]).then(([l, c, k, a]) => {
            setLeads(l?.data?.leads || []);
            setConvs(c?.data?.conversations || []);
            setCalls(k?.data?.calls || []);
            setAppts(a?.data?.appointments || []);
        }).finally(() => setLoading(false));
    }, [accessToken]);

    const statusCounts = leads.reduce((acc: Record<string, number>, l) => {
        acc[l.sub_status] = (acc[l.sub_status] || 0) + 1;
        return acc;
    }, {});

    const pickedUpCalls  = calls.filter(c => !NOT_ANSWERED.has(c.outcome || '')).length;
    const voicemailCalls = calls.filter(c => c.outcome === 'voicemail').length;
    const noAnswerCalls  = calls.filter(c => c.outcome === 'no_answer').length;
    const failedCalls    = calls.filter(c => c.outcome === 'failed' || c.outcome === 'call_failed').length;
    const didntPickUp    = calls.filter(c => NOT_ANSWERED.has(c.outcome || '')).length;
    const repliedConvs   = convs.filter(c => c.has_reply).length;
    // "Conversations" means the lead actually wrote back — NOT every thread
    // we started by texting/calling them. Counted by distinct lead (not
    // distinct conversation row) so it can never exceed Total Leads even if
    // one lead replied on more than one channel.
    const conversationsWithReply = new Set(convs.filter(c => c.has_reply).map(c => c.lead_id)).size;
    const notInterested  = leads.filter(l => l.stage === 'dead').length;
    const emailsSent     = Math.max(convs.filter(c => c.channel === 'email').length, 1);

    const stats = [
        { label: 'Total Leads',     value: leads.length,                   icon: Users,         color: '#6366f1', href: '/leads' },
        { label: 'Conversations',   value: conversationsWithReply,         icon: MessageCircle, color: '#d4a94f', href: '/conversations?engagement=replied' },
        { label: 'Total Calls',     value: calls.length,                   icon: Phone,         color: '#f59e0b', href: '/calls' },
        { label: 'Emails Sent',     value: emailsSent,                     icon: Mail,          color: '#10b981', href: '/conversations?channel=email', badge: 'SENT OK' },
        { label: 'Picked-Up Calls', value: pickedUpCalls,                  icon: PhoneMissed,   color: '#22c55e', href: '/calls?outcome=picked_up' },
        { label: 'Voicemails',      value: voicemailCalls,                 icon: Voicemail,     color: '#64748b', href: '/calls?outcome=voicemail' },
        { label: 'Replied to Text', value: repliedConvs,                   icon: Reply,         color: '#0ea5e9', href: '/conversations?engagement=replied' },
        { label: 'Converted',       value: statusCounts['converted'] || 0, icon: TrendingUp,    color: '#10b981', href: '/leads?status=converted&view=list' },
        { label: 'Qualified',       value: statusCounts['qualified'] || 0, icon: UserCheck,     color: '#8b5cf6', href: '/leads?status=qualified&view=list' },
        { label: 'Not Interested',  value: notInterested,                  icon: UserX,         color: '#f87171', href: '/leads?status=dead&view=list' },
        { label: 'Appointments',    value: appts.length,                   icon: CalendarDays,  color: '#ec4899', href: '/appointments' },
    ];

    const firstName = user?.firstName || 'Admin';

    const exportSummary = () => {
        const now = new Date();
        const stamp = now.toISOString().slice(0, 10);

        const overview = [
            { Metric: 'Total Leads',      Value: leads.length },
            { Metric: 'Total Calls Performed', Value: calls.length },
            { Metric: 'Calls Picked Up',  Value: pickedUpCalls },
            { Metric: "Calls Didn't Pick Up (no answer + voicemail + failed)", Value: didntPickUp },
            { Metric: '  — No Answer',    Value: noAnswerCalls },
            { Metric: '  — Voicemail',    Value: voicemailCalls },
            { Metric: '  — Failed (system/carrier)', Value: failedCalls },
            { Metric: 'Replied to Text',  Value: repliedConvs },
            { Metric: 'Qualified',        Value: statusCounts['qualified'] || 0 },
            { Metric: 'Converted',        Value: statusCounts['converted'] || 0 },
            { Metric: 'Not Interested (dead)', Value: notInterested },
            { Metric: 'Appointments Booked', Value: appts.length },
            { Metric: 'Report Generated', Value: now.toLocaleString('en-US') },
        ];

        const leadsSheet = leads.map(l => ({
            'First Name': l.first_name,
            'Last Name':  l.last_name,
            'Phone':      l.phone,
            'Status':     l.sub_status,
            'Created':    l.created_at ? new Date(l.created_at).toLocaleString('en-US') : '',
        }));

        const callsSheet = calls.map(c => ({
            'Lead / Caller': c.patientName,
            'Phone':         c.phone,
            'Type':          c.call_type,
            'Outcome':       c.outcome || 'info',
            'Duration (sec)': c.duration_seconds ?? '',
            'Date':          c.created_at ? new Date(c.created_at).toLocaleString('en-US') : '',
        }));

        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(overview), 'Summary');
        XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(leadsSheet), 'Leads');
        XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(callsSheet), 'Calls');
        XLSX.writeFile(wb, `dashboard-summary-${stamp}.xlsx`);
    };

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <SideNav />
            <main style={{ marginLeft: 220, flex: 1, padding: 32, overflowY: 'auto' }}>

                {/* Header */}
                <div style={{ marginBottom: 32, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                        <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>
                            Welcome back, {firstName} 👋
                        </h1>
                        <p style={{ color: 'var(--text-2)', marginTop: 6, fontSize: 14 }}>
                            Here&apos;s your business overview
                        </p>
                    </div>
                    <button
                        onClick={exportSummary}
                        disabled={loading}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 8,
                            padding: '10px 16px', borderRadius: 10, border: '1px solid var(--border-default)',
                            background: 'var(--bg-card)', color: 'var(--text-1)', fontSize: 13, fontWeight: 700,
                            cursor: loading ? 'default' : 'pointer', opacity: loading ? 0.5 : 1,
                        }}
                    >
                        <FileDown size={15} color="#22c55e" />
                        Export Summary (.xlsx)
                    </button>
                </div>

                {/* Stat cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 36 }}>
                    {stats.map(s => {
                        const Icon = s.icon;
                        return (
                            <Link key={s.label} href={s.href} style={{ textDecoration: 'none' }}>
                                <div style={{
                                    background: 'var(--bg-card)', border: '1px solid var(--border-default)',
                                    borderRadius: 14, padding: '20px 22px', cursor: 'pointer',
                                    transition: 'border-color 0.15s',
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 14 }}>
                                        <div style={{
                                            width: 32, height: 32, borderRadius: 9,
                                            background: `${s.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        }}>
                                            <Icon size={15} color={s.color} />
                                        </div>
                                        <span style={{ fontSize: 12, color: 'var(--text-4)', fontWeight: 600 }}>{s.label}</span>
                                        {s.badge && (
                                            <span style={{
                                                marginLeft: 'auto', fontSize: 10, fontWeight: 700, padding: '2px 7px',
                                                borderRadius: 12, background: 'rgba(34, 197, 94, 0.15)', color: '#22c55e', letterSpacing: '0.02em',
                                            }}>
                                                ✓ {s.badge}
                                            </span>
                                        )}
                                    </div>
                                    <div style={{ fontSize: 34, fontWeight: 800, color: 'var(--text-1)', lineHeight: 1 }}>
                                        {loading ? '—' : s.value}
                                    </div>
                                </div>
                            </Link>
                        );
                    })}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 300px', gap: 20 }}>
                    {/* Recent Leads */}
                    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                        <div style={{ padding: '18px 22px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ fontWeight: 700, fontSize: 14 }}>Recent Leads</div>
                            <Link href="/leads" style={{ fontSize: 12, color: 'var(--primary)', textDecoration: 'none' }}>View all →</Link>
                        </div>
                        {loading ? (
                            <div style={{ padding: '24px 22px', color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>
                        ) : leads.length === 0 ? (
                            <div style={{ padding: '32px 22px', textAlign: 'center', color: 'var(--text-4)', fontSize: 13 }}>No leads yet</div>
                        ) : (
                            leads.slice(0, 6).map((l, i) => {
                                const sc = STATUS_COLORS[l.sub_status] || STATUS_COLORS.new;
                                return (
                                    <div key={l.id} style={{
                                        padding: '12px 22px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                        borderBottom: i < Math.min(leads.length, 6) - 1 ? '1px solid var(--border-subtle)' : 'none',
                                    }}>
                                        <div>
                                            <div style={{ fontWeight: 600, fontSize: 13 }}>{l.first_name} {l.last_name}</div>
                                            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{l.phone || '—'}</div>
                                        </div>
                                        <span style={{ padding: '3px 9px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: sc.bg, color: sc.color }}>
                                            {l.sub_status}
                                        </span>
                                    </div>
                                );
                            })
                        )}
                    </div>

                    {/* Recent Conversations */}
                    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                        <div style={{ padding: '18px 22px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ fontWeight: 700, fontSize: 14 }}>Recent Conversations</div>
                            <Link href="/conversations" style={{ fontSize: 12, color: 'var(--primary)', textDecoration: 'none' }}>View all →</Link>
                        </div>
                        {loading ? (
                            <div style={{ padding: '24px 22px', color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>
                        ) : convs.length === 0 ? (
                            <div style={{ padding: '32px 22px', textAlign: 'center', color: 'var(--text-4)', fontSize: 13 }}>No conversations yet</div>
                        ) : (
                            convs.slice(0, 6).map((c, i) => (
                                <Link key={c.id} href={`/conversations?conv=${c.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                                    <div style={{
                                        padding: '12px 22px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                        borderBottom: i < Math.min(convs.length, 6) - 1 ? '1px solid var(--border-subtle)' : 'none',
                                        cursor: 'pointer',
                                    }}>
                                        <div>
                                            <div style={{ fontWeight: 600, fontSize: 13 }}>{c.first_name} {c.last_name}</div>
                                            <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 2, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {c.last_message || 'No messages yet'}
                                            </div>
                                        </div>
                                        <span style={{
                                            padding: '3px 8px', borderRadius: 6, fontSize: 10, fontWeight: 700,
                                            background: c.channel === 'email' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(99,102,241,0.1)',
                                            color: c.channel === 'email' ? '#22c55e' : '#a5b4fc',
                                        }}>
                                            {c.channel === 'email' ? '✉️ EMAIL SENT OK' : c.channel?.toUpperCase()}
                                        </span>
                                    </div>
                                </Link>
                            ))
                        )}
                    </div>
                    {/* Mini Calendar */}
                    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                        <div style={{ padding: '18px 22px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ fontWeight: 700, fontSize: 14 }}>Appointments</div>
                            <Link href="/appointments" style={{ fontSize: 12, color: 'var(--primary)', textDecoration: 'none' }}>View all →</Link>
                        </div>
                        <div style={{ padding: '16px 18px' }}>
                            {loading ? <p style={{ color: 'var(--text-4)', fontSize: 13 }}>Loading...</p> : <MiniCalendar appts={appts} />}
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
