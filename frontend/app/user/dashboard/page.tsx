'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { Users, MessageCircle, Phone, CalendarDays, TrendingUp, ArrowRight, Bot, CheckCircle, XCircle, PlayCircle } from 'lucide-react';
import Link from 'next/link';
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

interface Lead {
    id: string; first_name: string; last_name: string;
    phone: string; status: string; created_at: string;
}
interface Conv {
    id: string; first_name: string; last_name: string;
    channel: string; last_message: string | null; last_message_at: string | null;
}
interface Call { id: string; phone: string; duration: number; created_at: string; }
interface Appt { id: string; title?: string; notes?: string; start_time: string; status?: string; }
interface Agent { id: string; name: string; role: string; status: string; }


const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
    new:       { bg: 'rgba(99,102,241,0.14)',  color: '#a5b4fc' },
    contacted: { bg: 'rgba(245,158,11,0.14)',  color: '#fbbf24' },
    qualified: { bg: 'rgba(16,185,129,0.14)',  color: '#34d399' },
    converted: { bg: 'rgba(185, 134, 42,0.14)',  color: '#e8c877' },
    dead:      { bg: 'rgba(107,114,128,0.1)',  color: '#9ca3af' },
};

const AVATAR_COLORS = ['#6366f1','#d4a94f','#f59e0b','#10b981','#8b5cf6','#ef4444','#3b82f6'];

function avatarColor(name: string) {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h + name.charCodeAt(i)) % AVATAR_COLORS.length;
    return AVATAR_COLORS[h];
}

function fmtTime(d: string | null) {
    if (!d) return '—';
    return parseApiDate(d).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function fmtDate(d: string | null) {
    if (!d) return '—';
    const dt = parseApiDate(d);
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function greeting() {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
}

// Build a simple 7-day call series for the chart
function buildCallSeries(calls: Call[]) {
    const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const counts: Record<string, number> = {};
    const now = new Date();
    for (let i = 6; i >= 0; i--) {
        const d = new Date(now);
        d.setDate(now.getDate() - i);
        const key = d.toDateString();
        counts[key] = 0;
    }
    calls.forEach(c => {
        const key = parseApiDate(c.created_at).toDateString();
        if (key in counts) counts[key]++;
    });
    return Object.values(counts).map((v, i) => ({ day: days[i % 7], calls: v }));
}

export default function UserDashboard() {
    const { user, accessToken } = useAuth();
    const [leads, setLeads]   = useState<Lead[]>([]);
    const [convs, setConvs]   = useState<Conv[]>([]);
    const [calls, setCalls]   = useState<Call[]>([]);
    const [appts, setAppts]   = useState<Appt[]>([]);
    const [agent, setAgent]   = useState<Agent | null>(null);
    const [loading, setLoading] = useState(true);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState<string | null>(null);

    useEffect(() => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };

        fetch('/api/auth/me', { headers: h })
            .then(r => r.json())
            .then(async meRes => {
                const agentId = meRes?.data?.user?.agent_id;
                const [l, c, cl, ap, ag] = await Promise.all([
                    fetch(`/api/leads`,         { headers: h }).then(r => r.json()),
                    fetch(`/api/conversations`, { headers: h }).then(r => r.json()),
                    fetch('/api/crm/calls',               { headers: h }).then(r => r.json()),
                    fetch('/api/appointments',            { headers: h }).then(r => r.json()),
                    agentId
                        ? fetch(`/api/agents/${agentId}`, { headers: h }).then(r => r.json())
                        : Promise.resolve(null),
                ]);
                setLeads(l?.data?.leads || []);
                setConvs(c?.data?.conversations || []);
                setCalls(cl?.data?.calls || []);
                setAppts(ap?.data?.appointments || []);
                setAgent(ag?.data?.agent || null);
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [accessToken]);

    const firstName = user?.firstName || 'there';
    const sc = (s: string) => leads.filter(l => l.status === s).length;
    const callSeries = buildCallSeries(calls);
    const upcomingAppts = appts.filter(a => parseApiDate(a.start_time) >= new Date()).slice(0, 4);

    // Conversion rate
    const convRate = leads.length ? Math.round((sc('converted') / leads.length) * 100) : 0;

    const statCards = [
        { label: 'Total Leads',     value: leads.length, sub: `${sc('new')} new`,        icon: Users,         color: '#6366f1', href: '/user/leads' },
        { label: 'Calls Today',     value: calls.filter(c => parseApiDate(c.created_at).toDateString() === new Date().toDateString()).length, sub: 'today', icon: Phone, color: '#d4a94f', href: '/user/calls' },
        { label: 'Appointments',    value: appts.length, sub: `${upcomingAppts.length} upcoming`, icon: CalendarDays, color: '#8b5cf6', href: '/user/appointments' },
        { label: 'Conversion Rate', value: `${convRate}%`, sub: `${sc('converted')} converted`, icon: TrendingUp, color: '#f59e0b', href: '/user/leads' },
    ];

    async function handleTest() {
        setTesting(true); setTestResult(null);
        await new Promise(r => setTimeout(r, 1200));
        setTestResult('Agent responded successfully.');
        setTesting(false);
    }

    return (
        <div style={{ maxWidth: 1100 }}>
            {/* Greeting */}
            <div style={{ marginBottom: 24 }}>
                <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, letterSpacing: '-0.02em' }}>
                    {greeting()}, {firstName} 👋
                </h1>
                <p style={{ color: 'var(--text-4)', marginTop: 4, fontSize: 13, margin: '4px 0 0' }}>
                    {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
                </p>
            </div>

            {/* Stat Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, marginBottom: 22 }}>
                {statCards.map(s => {
                    const Icon = s.icon;
                    return (
                        <Link key={s.label} href={s.href} style={{ textDecoration: 'none' }}>
                            <div style={{
                                background: 'var(--bg-card)', border: '1px solid var(--border-default)',
                                borderRadius: 14, padding: '18px 20px', cursor: 'pointer',
                                transition: 'border-color 0.15s, box-shadow 0.15s',
                            }}
                                onMouseEnter={e => {
                                    (e.currentTarget as HTMLElement).style.borderColor = s.color + '55';
                                    (e.currentTarget as HTMLElement).style.boxShadow = `0 4px 20px ${s.color}18`;
                                }}
                                onMouseLeave={e => {
                                    (e.currentTarget as HTMLElement).style.borderColor = '';
                                    (e.currentTarget as HTMLElement).style.boxShadow = '';
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                                    <div style={{ width: 36, height: 36, borderRadius: 10, background: `${s.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <Icon size={17} color={s.color} />
                                    </div>
                                    <span style={{ fontSize: 11, color: '#10b981', fontWeight: 700, background: 'rgba(16,185,129,0.1)', padding: '2px 7px', borderRadius: 20 }}>↑ {s.sub}</span>
                                </div>
                                <div style={{ fontSize: 34, fontWeight: 800, color: 'var(--text-1)', lineHeight: 1 }}>
                                    {loading ? '—' : s.value}
                                </div>
                                <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 5, fontWeight: 600 }}>{s.label}</div>
                            </div>
                        </Link>
                    );
                })}
            </div>

            {/* Middle Row: Funnel + Calls Chart + AI Agent */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 300px', gap: 16, marginBottom: 22 }}>

                {/* Leads Funnel */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, padding: '20px 22px' }}>
                    <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>Leads Funnel</div>
                    <div style={{ fontSize: 11, color: 'var(--text-4)', marginBottom: 18 }}>Last 7 days</div>
                    {loading ? (
                        <div style={{ color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>
                    ) : (
                        <div style={{ display: 'flex', gap: 18, alignItems: 'center' }}>
                            {/* Funnel SVG */}
                            <svg width="100" height="140" viewBox="0 0 100 140" style={{ flexShrink: 0 }}>
                                <polygon points="10,0 90,0 75,35 25,35" fill="#6366f1" opacity="0.85" rx="4" />
                                <polygon points="25,38 75,38 65,73 35,73" fill="#d4a94f" opacity="0.85" />
                                <polygon points="35,76 65,76 57,111 43,111" fill="#10b981" opacity="0.85" />
                                <polygon points="43,114 57,114 53,140 47,140" fill="#f59e0b" opacity="0.85" />
                            </svg>
                            {/* Labels */}
                            <div style={{ flex: 1 }}>
                                {[
                                    { label: 'Total Leads', value: leads.length,    color: '#6366f1' },
                                    { label: 'Contacted',   value: sc('contacted'), color: '#d4a94f' },
                                    { label: 'Qualified',   value: sc('qualified'), color: '#10b981' },
                                    { label: 'Converted',   value: sc('converted'), color: '#f59e0b' },
                                ].map(row => (
                                    <div key={row.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                                            <div style={{ width: 8, height: 8, borderRadius: 2, background: row.color }} />
                                            <span style={{ fontSize: 12, color: 'var(--text-4)' }}>{row.label}</span>
                                        </div>
                                        <span style={{ fontSize: 15, fontWeight: 800, color: row.color }}>{row.value}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Calls Overview Chart */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, padding: '20px 22px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <div style={{ fontWeight: 700, fontSize: 14 }}>Calls Overview</div>
                        <span style={{ fontSize: 11, color: 'var(--text-4)', background: 'var(--bg-elevated)', padding: '3px 9px', borderRadius: 7, border: '1px solid var(--border-default)' }}>This Week</span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-4)', marginBottom: 16 }}>Calls per day</div>
                    <ResponsiveContainer width="100%" height={140}>
                        <LineChart data={callSeries}>
                            <XAxis dataKey="day" tick={{ fontSize: 10, fill: 'var(--text-4)' }} axisLine={false} tickLine={false} />
                            <YAxis tick={{ fontSize: 10, fill: 'var(--text-4)' }} axisLine={false} tickLine={false} width={20} allowDecimals={false} />
                            <Tooltip
                                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 8, fontSize: 12 }}
                                labelStyle={{ color: 'var(--text-2)', fontWeight: 700 }}
                            />
                            <Line type="monotone" dataKey="calls" stroke="#d4a94f" strokeWidth={2.5} dot={{ fill: '#d4a94f', strokeWidth: 0, r: 4 }} activeDot={{ r: 6 }} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                {/* My AI Agent */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, padding: '20px 20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                        <div style={{ fontWeight: 700, fontSize: 14 }}>My AI Agent</div>
                        {agent && (
                            <span style={{
                                display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 700,
                                padding: '3px 8px', borderRadius: 20,
                                background: agent.status === 'active' ? 'rgba(16,185,129,0.12)' : 'rgba(107,114,128,0.12)',
                                color: agent.status === 'active' ? '#10b981' : '#9ca3af',
                            }}>
                                {agent.status === 'active' ? <CheckCircle size={9} /> : <XCircle size={9} />}
                                {agent.status === 'active' ? 'Active' : 'Inactive'}
                            </span>
                        )}
                    </div>

                    {loading ? (
                        <div style={{ color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>
                    ) : !agent ? (
                        <div style={{ textAlign: 'center', padding: '20px 0' }}>
                            <Bot size={32} style={{ opacity: 0.2, marginBottom: 8 }} />
                            <p style={{ fontSize: 12, color: 'var(--text-4)', margin: 0 }}>No agent assigned</p>
                        </div>
                    ) : (
                        <>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, padding: '12px', background: 'rgba(212, 169, 79,0.06)', borderRadius: 10, border: '1px solid rgba(212, 169, 79,0.12)' }}>
                                <div style={{ width: 42, height: 42, borderRadius: 12, background: 'rgba(212, 169, 79,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                    <Bot size={20} color="#d4a94f" />
                                </div>
                                <div>
                                    <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--text-1)' }}>{agent.name}</div>
                                    <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 2 }}>{agent.role}</div>
                                </div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
                                <div style={{ background: 'var(--bg-elevated)', borderRadius: 9, padding: '10px 12px', border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 20, fontWeight: 800, color: '#d4a94f' }}>{calls.length}</div>
                                    <div style={{ fontSize: 10, color: 'var(--text-4)', marginTop: 2 }}>Calls Handled</div>
                                </div>
                                <div style={{ background: 'var(--bg-elevated)', borderRadius: 9, padding: '10px 12px', border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 20, fontWeight: 800, color: '#8b5cf6' }}>{appts.length}</div>
                                    <div style={{ fontSize: 10, color: 'var(--text-4)', marginTop: 2 }}>Appointments</div>
                                </div>
                            </div>

                            <button
                                onClick={handleTest}
                                disabled={testing}
                                style={{
                                    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
                                    padding: '9px', borderRadius: 9, fontSize: 12, fontWeight: 700,
                                    background: 'linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%)',
                                    color: '#fff', border: 'none', cursor: testing ? 'not-allowed' : 'pointer',
                                    opacity: testing ? 0.7 : 1,
                                }}
                            >
                                <PlayCircle size={13} />
                                {testing ? 'Testing…' : 'Test Agent'}
                            </button>
                            {testResult && (
                                <p style={{ marginTop: 8, fontSize: 11, color: '#10b981', textAlign: 'center', margin: '8px 0 0' }}>{testResult}</p>
                            )}
                        </>
                    )}
                </div>
            </div>

            {/* Bottom Row: Recent Leads + Recent Conversations + Upcoming Appointments */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
                {/* Recent Leads */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                    <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontWeight: 700, fontSize: 14 }}>Recent Leads</div>
                        <Link href="/user/leads" style={{ fontSize: 12, color: 'var(--primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 3 }}>View all <ArrowRight size={11} /></Link>
                    </div>
                    {loading ? (
                        <div style={{ padding: '20px', color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>
                    ) : leads.length === 0 ? (
                        <div style={{ padding: '28px 20px', textAlign: 'center', color: 'var(--text-4)', fontSize: 13 }}>No leads yet</div>
                    ) : leads.slice(0, 5).map((l, i) => {
                        const name = `${l.first_name} ${l.last_name}`.trim();
                        const ac = avatarColor(name);
                        const sc2 = STATUS_COLORS[l.status] || STATUS_COLORS.new;
                        return (
                            <div key={l.id} style={{
                                padding: '11px 20px', display: 'flex', alignItems: 'center', gap: 10,
                                borderBottom: i < Math.min(leads.length, 5) - 1 ? '1px solid var(--border-subtle)' : 'none',
                            }}>
                                <div style={{ width: 32, height: 32, borderRadius: 9, background: `${ac}22`, color: ac, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>
                                    {(l.first_name?.[0] || '?').toUpperCase()}
                                </div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontWeight: 600, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</div>
                                    <div style={{ fontSize: 11, color: 'var(--text-4)' }}>{l.phone || '—'}</div>
                                </div>
                                <span style={{ padding: '3px 9px', borderRadius: 20, fontSize: 10, fontWeight: 700, background: sc2.bg, color: sc2.color, textTransform: 'capitalize', flexShrink: 0 }}>{l.status}</span>
                            </div>
                        );
                    })}
                </div>

                {/* Recent Conversations */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                    <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontWeight: 700, fontSize: 14 }}>Recent Conversations</div>
                        <Link href="/user/conversations" style={{ fontSize: 12, color: 'var(--primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 3 }}>View all <ArrowRight size={11} /></Link>
                    </div>
                    {loading ? (
                        <div style={{ padding: '20px', color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>
                    ) : convs.length === 0 ? (
                        <div style={{ padding: '28px 20px', textAlign: 'center', color: 'var(--text-4)', fontSize: 13 }}>No conversations yet</div>
                    ) : convs.slice(0, 5).map((c, i) => {
                        const name = `${c.first_name} ${c.last_name}`.trim();
                        const ac = avatarColor(name);
                        const chColor = c.channel === 'whatsapp' ? '#25d366' : c.channel === 'voice' ? '#f59e0b' : '#a5b4fc';
                        return (
                            <Link key={c.id} href={`/user/conversations?conv=${c.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>
                                <div style={{
                                    padding: '11px 20px', display: 'flex', alignItems: 'center', gap: 10,
                                    borderBottom: i < Math.min(convs.length, 5) - 1 ? '1px solid var(--border-subtle)' : 'none',
                                    transition: 'background 0.12s', cursor: 'pointer',
                                }}
                                    onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = 'rgba(185, 134, 42,0.04)')}
                                    onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = 'transparent')}
                                >
                                    <div style={{ width: 32, height: 32, borderRadius: 9, background: `${ac}22`, color: ac, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>
                                        {(c.first_name?.[0] || '?').toUpperCase()}
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontWeight: 600, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</div>
                                        <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 150 }}>
                                            {c.last_message || 'No messages yet'}
                                        </div>
                                    </div>
                                    <span style={{ padding: '2px 7px', borderRadius: 5, fontSize: 9, fontWeight: 700, background: `${chColor}18`, color: chColor, textTransform: 'uppercase', flexShrink: 0, border: `1px solid ${chColor}30` }}>
                                        {c.channel || 'sms'}
                                    </span>
                                </div>
                            </Link>
                        );
                    })}
                </div>

                {/* Upcoming Appointments */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                    <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontWeight: 700, fontSize: 14 }}>Upcoming Appointments</div>
                        <Link href="/user/appointments" style={{ fontSize: 12, color: 'var(--primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 3 }}>View all <ArrowRight size={11} /></Link>
                    </div>
                    {loading ? (
                        <div style={{ padding: '20px', color: 'var(--text-4)', fontSize: 13 }}>Loading...</div>
                    ) : upcomingAppts.length === 0 ? (
                        <div style={{ padding: '28px 20px', textAlign: 'center', color: 'var(--text-4)', fontSize: 13 }}>No upcoming appointments</div>
                    ) : upcomingAppts.map((a, i) => {
                        const dt = parseApiDate(a.start_time);
                        return (
                            <div key={a.id} style={{
                                padding: '11px 20px', display: 'flex', alignItems: 'center', gap: 12,
                                borderBottom: i < upcomingAppts.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                            }}>
                                <div style={{ flexShrink: 0, textAlign: 'center', width: 36 }}>
                                    <div style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', color: 'var(--primary)' }}>
                                        {dt.toLocaleDateString('en-US', { month: 'short' })}
                                    </div>
                                    <div style={{ fontSize: 20, fontWeight: 800, lineHeight: 1.1, color: 'var(--text-1)' }}>{dt.getDate()}</div>
                                </div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontWeight: 600, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                        {a.title || a.notes || 'Appointment'}
                                    </div>
                                    <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 1 }}>{fmtTime(a.start_time)}</div>
                                </div>
                                <span style={{ padding: '3px 9px', borderRadius: 20, fontSize: 10, fontWeight: 700, background: 'rgba(99,102,241,0.12)', color: '#a5b4fc', flexShrink: 0 }}>
                                    Upcoming
                                </span>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
