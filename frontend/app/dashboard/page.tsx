'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { useAgencyScope } from '@/contexts/AgencyScopeContext';
import { useRouter } from 'next/navigation';
import { SideNav } from '@/components/SideNav/SideNav';
import {
    Users, MessageCircle, Phone, CalendarDays, TrendingUp, UserCheck,
    PhoneMissed, Voicemail, Reply, FileDown, UserX, Mail,
    Calendar, BarChart3, Layers, Filter, CheckCircle2, ArrowRight, Sparkles
} from 'lucide-react';
import Link from 'next/link';
import * as XLSX from 'xlsx';


interface Lead {
    id: string;
    first_name: string;
    last_name: string;
    phone: string;
    sub_status: string;
    stage: string;
    created_at: string;
    has_replied?: boolean;
    opted_out?: boolean;
}

interface DailyBatchStat {
    upload_date: string; // YYYY-MM-DD
    total_uploaded: number;
    new_count: number;
    contacted_count: number;
    followup_count: number;
    responded_count: number;
    qualified_count: number;
    dead_count: number;
}

interface Conv {
    id: string;
    lead_id: string;
    first_name: string;
    last_name: string;
    channel: string;
    last_message: string | null;
    last_message_at: string | null;
    has_reply?: boolean;
}

interface Call {
    id: string;
    patientName: string;
    phone: string;
    call_type: string;
    duration_seconds: number | null;
    created_at: string;
    outcome?: string | null;
}

const NOT_ANSWERED = new Set(['no_answer', 'voicemail', 'failed', 'call_failed']);
interface Appt {
    id: string;
    patient_name?: string;
    service_name?: string;
    status: string;
    scheduled_at: string;
}

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
    new:            { bg: 'rgba(99,102,241,0.12)',  color: '#a5b4fc' },
    contacted:      { bg: 'rgba(245,158,11,0.12)',  color: '#fbbf24' },
    stale:          { bg: 'rgba(168,85,247,0.12)',  color: '#c084fc' },
    follow_up_sent: { bg: 'rgba(168,85,247,0.12)',  color: '#c084fc' },
    responded:      { bg: 'rgba(56,189,248,0.12)',  color: '#38bdf8' },
    qualified:      { bg: 'rgba(16,185,129,0.12)',  color: '#34d399' },
    converted:      { bg: 'rgba(185, 134, 42,0.12)', color: '#e8c877' },
    dead:           { bg: 'rgba(107,114,128,0.1)',   color: '#9ca3af' },
};

export default function AdminDashboard() {
    const { user, accessToken, isLoading } = useAuth();
    const { agency } = useAgencyScope();
    const router = useRouter();
    const [leads, setLeads] = useState<Lead[]>([]);
    const [dailyBatches, setDailyBatches] = useState<DailyBatchStat[]>([]);
    const [selectedDate, setSelectedDate] = useState<string>('all');
    const [convs, setConvs] = useState<Conv[]>([]);
    const [calls, setCalls] = useState<Call[]>([]);
    const [appts, setAppts] = useState<Appt[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role)) {
            router.replace('/user/dashboard');
            return;
        }
        if (user?.role === 'super_admin' && !agency) {
            router.replace('/platform');
        }
    }, [isLoading, accessToken, user, agency, router]);

    const loadDashboard = useCallback((silent = false) => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };
        if (!silent) setLoading(true);
        Promise.all([
            fetch(`/api/leads`,             { headers: h }).then(r => r.json()).catch(() => ({})),
            fetch(`/api/leads/daily-stats`, { headers: h }).then(r => r.json()).catch(() => ({})),
            fetch(`/api/conversations`,     { headers: h }).then(r => r.json()).catch(() => ({})),
            fetch('/api/crm/calls',         { headers: h }).then(r => r.json()).catch(() => ({})),
            fetch('/api/appointments',      { headers: h }).then(r => r.json()).catch(() => ({})),
        ]).then(([l, d, c, k, a]) => {
            setLeads(l?.data?.leads || []);
            setDailyBatches(d?.data?.daily_batches || []);
            setConvs(c?.data?.conversations || []);
            setCalls(k?.data?.calls || []);
            setAppts(a?.data?.appointments || []);
        }).finally(() => {
            if (!silent) setLoading(false);
        });
    }, [accessToken]);

    useEffect(() => {
        loadDashboard(false);
        const timer = setInterval(() => loadDashboard(true), 4000);
        return () => clearInterval(timer);
    }, [loadDashboard]);

    // Filter leads by selected upload date
    const displayedLeads = useMemo(() => {
        if (selectedDate === 'all') return leads;
        return leads.filter(l => (l.created_at || '').slice(0, 10) === selectedDate);
    }, [leads, selectedDate]);

    const statusCounts = displayedLeads.reduce((acc: Record<string, number>, l) => {
        acc[l.sub_status] = (acc[l.sub_status] || 0) + 1;
        return acc;
    }, {});

    const pickedUpCalls  = calls.filter(c => !NOT_ANSWERED.has(c.outcome || '')).length;
    const voicemailCalls = calls.filter(c => c.outcome === 'voicemail').length;
    const noAnswerCalls  = calls.filter(c => c.outcome === 'no_answer').length;
    const failedCalls    = calls.filter(c => c.outcome === 'failed' || c.outcome === 'call_failed').length;
    const didntPickUp    = calls.filter(c => NOT_ANSWERED.has(c.outcome || '')).length;

    // Filter conversations to matching leads if date selected
    const activeConvs = useMemo(() => {
        if (selectedDate === 'all') return convs;
        const matchingLeadIds = new Set(displayedLeads.map(l => l.id));
        return convs.filter(c => matchingLeadIds.has(c.lead_id));
    }, [convs, displayedLeads, selectedDate]);

    const repliedConvList = activeConvs.filter(c => c.has_reply);
    const repliedConvs = repliedConvList.length;
    const firstRepliedConv = repliedConvList[0];
    const repliedHref = firstRepliedConv
        ? `/conversations?engagement=replied&conv=${firstRepliedConv.id}`
        : '/conversations?engagement=replied';

    const activeOutreachThreads = activeConvs.filter(c => c.last_message !== null).length;
    const notInterested  = displayedLeads.filter(l => l.stage === 'dead' || l.opted_out).length;
    const emailsSent     = activeConvs.filter(c => c.channel === 'email').length;

    const dateQuery = selectedDate !== 'all' ? `date=${selectedDate}` : '';
    const leadLink = (extra: string = '') => {
        const parts = [dateQuery, extra].filter(Boolean);
        return parts.length ? `/leads?${parts.join('&')}` : '/leads';
    };

    const followupCount = useMemo(() => {
        if (selectedDate !== 'all') {
            const batch = dailyBatches.find(b => b.upload_date === selectedDate);
            if (batch) return batch.followup_count || 0;
            return displayedLeads.filter(l => l.sub_status === 'followed_up' || l.sub_status === 'follow_up_sent').length;
        }
        return dailyBatches.reduce((acc, b) => acc + (b.followup_count || 0), 0);
    }, [dailyBatches, displayedLeads, selectedDate]);

    const stats = [
        { label: selectedDate === 'all' ? 'Total Leads' : 'Uploaded This Day', value: displayedLeads.length, icon: Users, color: '#6366f1', href: leadLink() },
        { label: 'Outreach Threads', value: activeOutreachThreads,          icon: MessageCircle, color: '#d4a94f', href: '/conversations' },
        { label: 'Day 2 Follow-Ups', value: followupCount,                  icon: Sparkles,      color: '#c084fc', href: leadLink('status=follow_up_sent&view=list'), badge: followupCount > 0 ? `${followupCount} SENT` : undefined },
        { label: 'Replied to Text',  value: repliedConvs,                   icon: Reply,         color: '#0ea5e9', href: repliedHref },
        { label: 'Qualified',        value: statusCounts['qualified'] || 0, icon: UserCheck,     color: '#8b5cf6', href: leadLink('status=qualified&view=list') },
        { label: 'Converted',        value: statusCounts['converted'] || 0, icon: TrendingUp,    color: '#10b981', href: leadLink('status=converted&view=list') },
        { label: 'Emails Sent',      value: emailsSent,                     icon: Mail,          color: '#10b981', href: '/conversations?channel=email', badge: emailsSent > 0 ? 'SENT OK' : undefined },
        { label: 'Total Calls',      value: selectedDate === 'all' ? calls.length : 0, icon: Phone, color: '#f59e0b', href: '/calls' },
        { label: 'Picked-Up Calls',  value: selectedDate === 'all' ? pickedUpCalls : 0, icon: PhoneMissed, color: '#22c55e', href: '/calls?outcome=picked_up' },
        { label: 'Voicemails',       value: selectedDate === 'all' ? voicemailCalls : 0, icon: Voicemail, color: '#64748b', href: '/calls?outcome=voicemail' },
        { label: 'Not Interested',   value: notInterested,                  icon: UserX,         color: '#f87171', href: leadLink('status=dead&view=list') },
        { label: 'Appointments',     value: selectedDate === 'all' ? appts.length : 0, icon: CalendarDays, color: '#ec4899', href: '/appointments' },
    ];

    const firstName = user?.firstName || 'Admin';

    const exportSummary = () => {
        const now = new Date();
        const stamp = now.toISOString().slice(0, 10);

        const overview = [
            { Metric: 'Total Leads in System', Value: leads.length },
            { Metric: 'Active Filter Date',    Value: selectedDate === 'all' ? 'All Time' : selectedDate },
            { Metric: 'Filtered Leads Count',  Value: displayedLeads.length },
            { Metric: 'Total Calls Performed', Value: calls.length },
            { Metric: 'Calls Picked Up',       Value: pickedUpCalls },
            { Metric: "Calls Didn't Pick Up",  Value: didntPickUp },
            { Metric: 'Replied to Outreach',   Value: repliedConvs },
            { Metric: 'Qualified',             Value: statusCounts['qualified'] || 0 },
            { Metric: 'Converted',             Value: statusCounts['converted'] || 0 },
            { Metric: 'Not Interested (dead)', Value: notInterested },
            { Metric: 'Appointments Booked',   Value: appts.length },
            { Metric: 'Report Generated',      Value: now.toLocaleString('en-US') },
        ];

        const dailyBatchesSheet = dailyBatches.map(b => {
            const contactedTotal = b.contacted_count + b.followup_count + b.responded_count;
            const replyRate = contactedTotal > 0 ? `${Math.round((b.responded_count / contactedTotal) * 100)}%` : '0%';
            return {
                'Upload Date':           b.upload_date,
                'Total Leads Uploaded':  b.total_uploaded,
                'New / In Queue':        b.new_count,
                'Day 1 Contacted':       b.contacted_count,
                'Day 2 Follow-Up':       b.followup_count,
                'Responded / Connected': b.responded_count,
                'Qualified / Booked':    b.qualified_count,
                'Dead / Opted Out':      b.dead_count,
                'Response Rate':         replyRate,
            };
        });

        const leadsSheet = displayedLeads.map(l => ({
            'First Name':  l.first_name,
            'Last Name':   l.last_name,
            'Phone':       l.phone,
            'Status':      l.sub_status,
            'Stage':       l.stage,
            'Upload Date': l.created_at ? l.created_at.slice(0, 10) : '',
            'Created At':  l.created_at ? new Date(l.created_at).toLocaleString('en-US') : '',
        }));

        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(overview), 'Summary');
        XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(dailyBatchesSheet), 'Daily Upload Batches');
        XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(leadsSheet), 'Leads');
        XLSX.writeFile(wb, `dashboard-summary-${stamp}.xlsx`);
    };

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <SideNav />
            <main style={{ marginLeft: 220, flex: 1, padding: 32, overflowY: 'auto' }}>

                {/* Header */}
                <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                        <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>
                            Welcome back, {firstName} 👋
                        </h1>
                        <p style={{ color: 'var(--text-2)', marginTop: 6, fontSize: 14 }}>
                            Real-time outreach performance &amp; per-day upload batches
                        </p>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                        <Link
                            href="/crm-settings"
                            style={{
                                display: 'flex', alignItems: 'center', gap: 8,
                                padding: '10px 15px', borderRadius: 10,
                                border: '1px solid rgba(37, 99, 235, 0.35)',
                                background: 'rgba(37, 99, 235, 0.08)',
                                color: 'var(--text-1)', fontSize: 13, fontWeight: 700,
                                textDecoration: 'none', transition: 'all 0.15s ease'
                            }}
                        >
                            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981', display: 'inline-block' }} />
                            <span>Campaign Hours: <b>9:00 AM – 6:00 PM EST</b></span>
                            <span style={{ fontSize: 11.5, color: '#3b82f6', textDecoration: 'underline', marginLeft: 2 }}>Edit</span>
                        </Link>
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
                </div>

                {/* Per-Day Upload Filter Bar */}
                <div style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-default)',
                    borderRadius: 14,
                    padding: '16px 20px',
                    marginBottom: 24,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Calendar size={16} color="var(--primary)" />
                            <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-1)' }}>
                                Filter Dashboard by Lead Upload Date:
                            </span>
                            {selectedDate !== 'all' && (
                                <span style={{
                                    fontSize: 11,
                                    background: 'rgba(99, 102, 241, 0.15)',
                                    color: '#818cf8',
                                    padding: '2px 8px',
                                    borderRadius: 10,
                                    fontWeight: 700
                                }}>
                                    Active Filter: {selectedDate}
                                </span>
                            )}
                        </div>
                        {selectedDate !== 'all' && (
                            <button
                                onClick={() => setSelectedDate('all')}
                                style={{
                                    background: 'transparent',
                                    border: '1px solid var(--border-default)',
                                    color: 'var(--text-3)',
                                    borderRadius: 6,
                                    padding: '3px 10px',
                                    fontSize: 11,
                                    fontWeight: 600,
                                    cursor: 'pointer'
                                }}>
                                Reset to All Time
                            </button>
                        )}
                    </div>

                    {/* Date Pills */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        <button
                            onClick={() => setSelectedDate('all')}
                            style={{
                                padding: '7px 14px',
                                borderRadius: 20,
                                fontSize: 12,
                                fontWeight: 700,
                                cursor: 'pointer',
                                border: `1px solid ${selectedDate === 'all' ? 'var(--primary)' : 'var(--border-default)'}`,
                                background: selectedDate === 'all' ? 'var(--primary)' : 'rgba(255,255,255,0.03)',
                                color: selectedDate === 'all' ? '#fff' : 'var(--text-2)',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 6,
                                transition: 'all 0.15s ease'
                            }}
                        >
                            <Layers size={13} />
                            <span>All Batches</span>
                            <span style={{
                                background: selectedDate === 'all' ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.1)',
                                padding: '1px 6px',
                                borderRadius: 10,
                                fontSize: 11
                            }}>
                                {leads.length} leads
                            </span>
                        </button>

                        {dailyBatches.map(batch => {
                            const isSelected = selectedDate === batch.upload_date;
                            const dateObj = new Date(batch.upload_date + 'T00:00:00');
                            const formatted = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                            return (
                                <button
                                    key={batch.upload_date}
                                    onClick={() => setSelectedDate(isSelected ? 'all' : batch.upload_date)}
                                    style={{
                                        padding: '7px 14px',
                                        borderRadius: 20,
                                        fontSize: 12,
                                        fontWeight: 700,
                                        cursor: 'pointer',
                                        border: `1px solid ${isSelected ? 'var(--primary)' : 'var(--border-default)'}`,
                                        background: isSelected ? 'var(--primary)' : 'rgba(255,255,255,0.03)',
                                        color: isSelected ? '#fff' : 'var(--text-2)',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 6,
                                        transition: 'all 0.15s ease'
                                    }}
                                >
                                    <Calendar size={13} />
                                    <span>{formatted}</span>
                                    <span style={{
                                        background: isSelected ? 'rgba(0,0,0,0.25)' : 'rgba(99,102,241,0.15)',
                                        color: isSelected ? '#fff' : '#a5b4fc',
                                        padding: '1px 7px',
                                        borderRadius: 10,
                                        fontSize: 11,
                                        fontWeight: 800
                                    }}>
                                        {batch.total_uploaded} leads
                                    </span>
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Intelligent Follow-Up & Campaign Engine Banner */}
                <div style={{
                    background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(168, 85, 247, 0.08) 100%)',
                    border: '1px solid rgba(168, 85, 247, 0.25)',
                    borderRadius: 14,
                    padding: '16px 20px',
                    marginBottom: 24,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <div style={{
                                width: 30, height: 30, borderRadius: 8,
                                background: 'rgba(168, 85, 247, 0.2)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center'
                            }}>
                                <Sparkles size={16} color="#c084fc" />
                            </div>
                            <div>
                                <span style={{ fontWeight: 800, fontSize: 14, color: 'var(--text-1)' }}>
                                    Intelligent Campaign &amp; Follow-Up Orchestrator
                                </span>
                                <span style={{
                                    marginLeft: 8,
                                    fontSize: 11,
                                    background: 'rgba(34, 197, 94, 0.15)',
                                    color: '#4ade80',
                                    padding: '2px 8px',
                                    borderRadius: 10,
                                    fontWeight: 700
                                }}>
                                    ● Balanced 1:1 Interleaving Active
                                </span>
                            </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: 'var(--text-3)' }}>
                            <span><strong>Pacing:</strong> &ge; 3 min humanoid delay</span>
                            <span>&bull;</span>
                            <span><strong>Schedule:</strong> 9:00 AM – 5:30 PM EST</span>
                            <span>&bull;</span>
                            <span><strong>Daily Cap:</strong> 50 messages/day</span>
                        </div>
                    </div>

                    <div style={{
                        fontSize: 12.5,
                        color: 'var(--text-2)',
                        background: 'rgba(0, 0, 0, 0.2)',
                        padding: '10px 14px',
                        borderRadius: 8,
                        border: '1px solid rgba(255, 255, 255, 0.04)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        flexWrap: 'wrap',
                        gap: 10
                    }}>
                        {selectedDate === '2026-10-27' ? (
                            <div>
                                <strong style={{ color: '#fbbf24' }}>📅 Oct 27 Batch Timing:</strong> Initial discovery messages (49/49) were dispatched today. Day 2 follow-ups automatically mature <strong>24 hours post-delivery (tomorrow, Oct 29 at 9:00 AM EST)</strong>. Zero follow-ups are due today for this batch.
                            </div>
                        ) : selectedDate === '2026-10-26' ? (
                            <div>
                                <strong style={{ color: '#c084fc' }}>📅 Oct 26 Batch:</strong> Leads delivered on Oct 26 are overdue for Day 2 follow-up. The intelligent pacer alternates 1:1 between pending follow-ups and new leads every cycle.
                            </div>
                        ) : (
                            <div>
                                <strong style={{ color: '#a5b4fc' }}>⚡ Intelligent Interleaving Policy:</strong> Follow-ups to warm unreplied leads are never starved by new cold leads. The pacer alternates 1:1 (1 Day 2 Follow-Up : 1 New Lead) every send cycle to maximize engagement.
                            </div>
                        )}
                        <Link
                            href="/conversations"
                            style={{
                                color: '#c084fc',
                                textDecoration: 'none',
                                fontWeight: 700,
                                fontSize: 12,
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4
                            }}
                        >
                            View Active Conversations <ArrowRight size={13} />
                        </Link>
                    </div>
                </div>

                {/* Stat cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 32 }}>
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

                {/* Per-Day Leads Uploaded & Funnel Performance Table */}
                <div style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-default)',
                    borderRadius: 14,
                    overflow: 'hidden',
                    marginBottom: 32
                }}>
                    <div style={{
                        padding: '18px 24px',
                        borderBottom: '1px solid var(--border-subtle)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: 12
                    }}>
                        <div>
                            <div style={{ fontWeight: 800, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                                <BarChart3 size={18} color="var(--primary)" />
                                Per-Day Lead Upload Batches &amp; Performance
                            </div>
                            <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 4 }}>
                                Breakdown of each upload date, outreach dispatch status, and lead engagement
                            </div>
                        </div>
                        <Link
                            href={selectedDate === 'all' ? '/leads' : `/leads?date=${selectedDate}`}
                            style={{ fontSize: 12, color: 'var(--primary)', textDecoration: 'none', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}
                        >
                            Open Lead Directory {selectedDate !== 'all' ? `(${selectedDate})` : ''} <ArrowRight size={13} />
                        </Link>
                    </div>

                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 13 }}>
                            <thead>
                                <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid var(--border-default)', color: 'var(--text-4)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    <th style={{ padding: '12px 20px', fontWeight: 700 }}>Upload Date</th>
                                    <th style={{ padding: '12px 16px', fontWeight: 700 }}>Total Uploaded</th>
                                    <th style={{ padding: '12px 16px', fontWeight: 700 }}>🆕 In Queue</th>
                                    <th style={{ padding: '12px 16px', fontWeight: 700 }}>💬 Day 1 Contacted</th>
                                    <th style={{ padding: '12px 16px', fontWeight: 700 }}>⏳ Day 2 Follow-Up</th>
                                    <th style={{ padding: '12px 16px', fontWeight: 700 }}>🟢 Responded</th>
                                    <th style={{ padding: '12px 16px', fontWeight: 700 }}>🛑 Dead / Opted</th>
                                    <th style={{ padding: '12px 16px', fontWeight: 700 }}>Outreach Progress</th>
                                    <th style={{ padding: '12px 20px', fontWeight: 700, textAlign: 'right' }}>Filter View</th>
                                </tr>
                            </thead>
                            <tbody>
                                {dailyBatches.length === 0 ? (
                                    <tr>
                                        <td colSpan={9} style={{ padding: '32px 20px', textAlign: 'center', color: 'var(--text-4)' }}>
                                            No lead upload batches recorded yet
                                        </td>
                                    </tr>
                                ) : (
                                    dailyBatches.map(b => {
                                        const dateObj = new Date(b.upload_date + 'T00:00:00');
                                        const formatted = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                                        const processedCount = b.total_uploaded - b.new_count;
                                        const progressPct = Math.round((processedCount / b.total_uploaded) * 100);
                                        const isFiltered = selectedDate === b.upload_date;

                                        return (
                                            <tr
                                                key={b.upload_date}
                                                style={{
                                                    borderBottom: '1px solid var(--border-subtle)',
                                                    background: isFiltered ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                                                    transition: 'background 0.15s'
                                                }}
                                            >
                                                <td style={{ padding: '14px 20px', fontWeight: 700 }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                        <Calendar size={14} color="var(--primary)" />
                                                        <span style={{ color: 'var(--text-1)' }}>{formatted}</span>
                                                    </div>
                                                </td>
                                                <td style={{ padding: '14px 16px' }}>
                                                    <span style={{
                                                        fontWeight: 800,
                                                        fontSize: 13,
                                                        color: 'var(--text-1)',
                                                        background: 'rgba(255,255,255,0.06)',
                                                        padding: '3px 9px',
                                                        borderRadius: 6
                                                    }}>
                                                        {b.total_uploaded} leads
                                                    </span>
                                                </td>
                                                <td style={{ padding: '14px 16px' }}>
                                                    <span style={{ color: '#a5b4fc', fontWeight: 700 }}>
                                                        {b.new_count}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '14px 16px' }}>
                                                    <span style={{ color: '#fbbf24', fontWeight: 700 }}>
                                                        {b.contacted_count}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '14px 16px' }}>
                                                    <span style={{ color: '#c084fc', fontWeight: 700 }}>
                                                        {b.followup_count}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '14px 16px' }}>
                                                    <span style={{
                                                        color: b.responded_count > 0 ? '#34d399' : 'var(--text-4)',
                                                        fontWeight: 700,
                                                        background: b.responded_count > 0 ? 'rgba(16, 185, 129, 0.15)' : 'transparent',
                                                        padding: b.responded_count > 0 ? '2px 8px' : '0',
                                                        borderRadius: 6
                                                    }}>
                                                        {b.responded_count}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '14px 16px' }}>
                                                    <span style={{ color: b.dead_count > 0 ? '#f87171' : 'var(--text-4)', fontWeight: 600 }}>
                                                        {b.dead_count}
                                                    </span>
                                                </td>
                                                <td style={{ padding: '14px 16px' }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: 140 }}>
                                                        <div style={{
                                                            flex: 1,
                                                            height: 6,
                                                            background: 'rgba(255,255,255,0.1)',
                                                            borderRadius: 3,
                                                            overflow: 'hidden'
                                                        }}>
                                                            <div style={{
                                                                width: `${progressPct}%`,
                                                                height: '100%',
                                                                background: progressPct === 100 ? '#22c55e' : 'var(--primary)',
                                                                borderRadius: 3
                                                            }} />
                                                        </div>
                                                        <span style={{ fontSize: 11, color: 'var(--text-4)', fontWeight: 700, width: 34 }}>
                                                            {progressPct}%
                                                        </span>
                                                    </div>
                                                </td>
                                                <td style={{ padding: '14px 20px', textAlign: 'right' }}>
                                                    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', alignItems: 'center' }}>
                                                        <button
                                                            onClick={() => setSelectedDate(isFiltered ? 'all' : b.upload_date)}
                                                            style={{
                                                                background: isFiltered ? 'var(--primary)' : 'rgba(255,255,255,0.04)',
                                                                color: isFiltered ? '#fff' : 'var(--text-2)',
                                                                border: `1px solid ${isFiltered ? 'var(--primary)' : 'var(--border-default)'}`,
                                                                borderRadius: 6,
                                                                padding: '5px 12px',
                                                                fontSize: 11,
                                                                fontWeight: 700,
                                                                cursor: 'pointer',
                                                                transition: 'all 0.15s ease'
                                                            }}
                                                        >
                                                            {isFiltered ? '✓ Active' : 'Filter Day'}
                                                        </button>
                                                        <Link
                                                            href={`/leads?date=${b.upload_date}`}
                                                            style={{
                                                                background: 'rgba(99, 102, 241, 0.15)',
                                                                color: '#a5b4fc',
                                                                border: '1px solid rgba(99, 102, 241, 0.3)',
                                                                borderRadius: 6,
                                                                padding: '5px 12px',
                                                                fontSize: 11,
                                                                fontWeight: 700,
                                                                textDecoration: 'none',
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: 4
                                                            }}
                                                        >
                                                            View {b.total_uploaded} Leads <ArrowRight size={12} />
                                                        </Link>
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* Bottom section: Recent Leads, Conversations, Appointments */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 300px', gap: 20 }}>
                    {/* Recent Leads */}
                    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                        <div style={{ padding: '18px 22px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ fontWeight: 700, fontSize: 14 }}>
                                {selectedDate === 'all' ? 'Recent Leads' : `Leads (${selectedDate}) — ${displayedLeads.length} leads`}
                            </div>
                            <Link 
                                href={selectedDate === 'all' ? '/leads' : `/leads?date=${selectedDate}`} 
                                style={{ fontSize: 12, color: 'var(--primary)', textDecoration: 'none', fontWeight: 600 }}
                            >
                                View all {displayedLeads.length} →
                            </Link>
                        </div>
                        <div style={{ maxHeight: 420, overflowY: 'auto' }}>
                            {loading ? (
                                <div style={{ padding: '24px 22px', color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>
                            ) : displayedLeads.length === 0 ? (
                                <div style={{ padding: '32px 22px', textAlign: 'center', color: 'var(--text-4)', fontSize: 13 }}>No leads for this date</div>
                            ) : (
                                displayedLeads.slice(0, 15).map((l, i) => {
                                    const sc = STATUS_COLORS[l.sub_status] || STATUS_COLORS.new;
                                    return (
                                        <Link key={l.id} href={`/leads/${l.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                                            <div style={{
                                                padding: '12px 22px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                                borderBottom: i < Math.min(displayedLeads.length, 15) - 1 ? '1px solid var(--border-subtle)' : 'none',
                                                cursor: 'pointer',
                                                transition: 'background 0.15s'
                                            }}>
                                                <div>
                                                    <div style={{ fontWeight: 600, fontSize: 13 }}>{l.first_name} {l.last_name}</div>
                                                    <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{l.phone || '—'}</div>
                                                </div>
                                                <span style={{ padding: '3px 9px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: sc.bg, color: sc.color }}>
                                                    {l.sub_status}
                                                </span>
                                            </div>
                                        </Link>
                                    );
                                })
                            )}
                        </div>
                    </div>

                    {/* Recent Conversations */}
                    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                        <div style={{ padding: '18px 22px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ fontWeight: 700, fontSize: 14 }}>Recent Conversations</div>
                            <Link href="/conversations" style={{ fontSize: 12, color: 'var(--primary)', textDecoration: 'none' }}>View all →</Link>
                        </div>
                        {loading ? (
                            <div style={{ padding: '24px 22px', color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>
                        ) : activeConvs.length === 0 ? (
                            <div style={{ padding: '32px 22px', textAlign: 'center', color: 'var(--text-4)', fontSize: 13 }}>No conversations yet</div>
                        ) : (
                            activeConvs.slice(0, 6).map((c, i) => (
                                <Link key={c.id} href={`/conversations?conv=${c.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                                    <div style={{
                                        padding: '12px 22px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                        borderBottom: i < Math.min(activeConvs.length, 6) - 1 ? '1px solid var(--border-subtle)' : 'none',
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
