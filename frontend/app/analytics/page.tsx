'use client';

import { Fragment, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { SideNav } from '@/components/SideNav/SideNav';
import { hasModuleAccess } from '@/lib/permissions';
import { parseApiDate } from '@/lib/date';
import { Phone, CalendarDays, Users, MessageCircle, RefreshCw, TrendingUp, TrendingDown, Minus, AlertTriangle, Lightbulb } from 'lucide-react';
import {
    ResponsiveContainer, ComposedChart, Area, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
    PieChart, Pie, Cell, FunnelChart, Funnel, LabelList, BarChart,
} from 'recharts';

interface Lead {
    id: string; first_name?: string; last_name?: string; sub_status: string; stage: string;
    created_at: string; updated_at?: string; tags: string[]; source?: string; phone?: string;
}
interface Call {
    id: string; call_type: string; direction?: string; duration_seconds: number | null;
    created_at: string; outcome?: string | null; phone?: string; patientName?: string;
}
interface Appt {
    id: string; status: string; created_at: string; start_time?: string; service_name?: string;
    first_name?: string; last_name?: string;
}
interface Conv { id: string; channel: string; ai_active: boolean; created_at: string; }

type RangeKey = '7d' | '30d' | '90d' | 'all';
const RANGE_LABELS: Record<RangeKey, string> = { '7d': '7D', '30d': '30D', '90d': '90D', all: 'All Time' };

const PALETTE = {
    indigo: '#818cf8', gold: '#d4a94f', sky: '#38bdf8', green: '#34d399',
    amber: '#e8c877', red: '#f87171', purple: '#8b5cf6', orange: '#fb923c',
    teal: '#2dd4bf', slate: '#94a3b8',
};

const STAGE_META: { key: string; label: string; color: string }[] = [
    { key: 'new_lead',  label: 'New Lead',  color: PALETTE.indigo },
    { key: 'old_lead',  label: 'Old Lead',  color: PALETTE.orange },
    { key: 'connected', label: 'Connected', color: PALETTE.sky },
    { key: 'quoted',    label: 'Quoted',    color: PALETTE.green },
    { key: 'closed',    label: 'Closed',    color: PALETTE.amber },
    { key: 'dead',      label: 'Trip Lead', color: PALETTE.red },
];

const OUTCOME_META: Record<string, { label: string; color: string }> = {
    confirmed:             { label: 'Confirmed',    color: PALETTE.green },
    reschedule_requested:  { label: 'Rescheduled',  color: PALETTE.amber },
    no_answer:             { label: 'No Answer',    color: PALETTE.slate },
    voicemail:             { label: 'Voicemail',    color: PALETTE.sky },
    cancelled:             { label: 'Cancelled',    color: PALETTE.red },
    failed:                { label: 'Failed',       color: PALETTE.red },
    info:                  { label: 'Information',  color: PALETTE.purple },
};

interface Bucket { label: string; start: Date; end: Date; }

function buildBuckets(range: RangeKey): Bucket[] {
    const now = new Date();
    if (range === '7d' || range === '30d') {
        const n = range === '7d' ? 7 : 30;
        return Array.from({ length: n }, (_, i) => {
            const start = new Date(now); start.setHours(0, 0, 0, 0); start.setDate(start.getDate() - (n - 1 - i));
            const end = new Date(start); end.setDate(end.getDate() + 1);
            return { label: start.toLocaleDateString('en-US', n <= 7 ? { weekday: 'short' } : { month: 'short', day: 'numeric' }), start, end };
        });
    }
    if (range === '90d') {
        const weeks = 13;
        return Array.from({ length: weeks }, (_, i) => {
            const end = new Date(now); end.setHours(23, 59, 59, 999); end.setDate(end.getDate() - (weeks - 1 - i) * 7);
            const start = new Date(end); start.setDate(start.getDate() - 6); start.setHours(0, 0, 0, 0);
            return { label: start.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), start, end };
        });
    }
    // all -> last 12 months
    return Array.from({ length: 12 }, (_, i) => {
        const start = new Date(now.getFullYear(), now.getMonth() - (11 - i), 1);
        const end = new Date(now.getFullYear(), now.getMonth() - (11 - i) + 1, 1);
        return { label: start.toLocaleDateString('en-US', { month: 'short' }), start, end };
    });
}

function extendBucketsForward(range: RangeKey, count: number): Bucket[] {
    const now = new Date();
    if (range === '7d' || range === '30d') {
        return Array.from({ length: count }, (_, i) => {
            const start = new Date(now); start.setHours(0, 0, 0, 0); start.setDate(start.getDate() + i + 1);
            const end = new Date(start); end.setDate(end.getDate() + 1);
            return { label: start.toLocaleDateString('en-US', range === '7d' ? { weekday: 'short' } : { month: 'short', day: 'numeric' }), start, end };
        });
    }
    if (range === '90d') {
        return Array.from({ length: count }, (_, i) => {
            const start = new Date(now); start.setHours(0, 0, 0, 0); start.setDate(start.getDate() + i * 7 + 1);
            const end = new Date(start); end.setDate(end.getDate() + 7);
            return { label: start.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), start, end };
        });
    }
    return Array.from({ length: count }, (_, i) => {
        const start = new Date(now.getFullYear(), now.getMonth() + i + 1, 1);
        const end = new Date(now.getFullYear(), now.getMonth() + i + 2, 1);
        return { label: start.toLocaleDateString('en-US', { month: 'short' }), start, end };
    });
}

/** Least-squares linear fit over an evenly-spaced series; returns the slope and the next `steps` projected values. */
function linearForecast(series: number[], steps: number): { slope: number; forecast: number[] } {
    const n = series.length;
    if (n < 2) return { slope: 0, forecast: Array(steps).fill(series[n - 1] ?? 0) };
    const meanX = (n - 1) / 2;
    const meanY = series.reduce((a, b) => a + b, 0) / n;
    let num = 0, den = 0;
    series.forEach((y, x) => { num += (x - meanX) * (y - meanY); den += (x - meanX) ** 2; });
    const slope = den === 0 ? 0 : num / den;
    const intercept = meanY - slope * meanX;
    return { slope, forecast: Array.from({ length: steps }, (_, i) => Math.max(0, Math.round(intercept + slope * (n + i)))) };
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const TIME_SLOTS = [
    { key: 'morning',   label: 'Morning (6–12)' },
    { key: 'afternoon', label: 'Afternoon (12–5)' },
    { key: 'evening',   label: 'Evening (5–9)' },
    { key: 'night',     label: 'Night (9pm–6am)' },
];
function slotFor(hour: number) {
    if (hour >= 6 && hour < 12) return 'morning';
    if (hour >= 12 && hour < 17) return 'afternoon';
    if (hour >= 17 && hour < 21) return 'evening';
    return 'night';
}

function StatCard({ label, value, icon: Icon, color, sub, delta }: {
    label: string; value: string | number; icon: any; color: string; sub?: string; delta?: number | null;
}) {
    const DeltaIcon = delta == null || delta === 0 ? Minus : delta > 0 ? TrendingUp : TrendingDown;
    const deltaColor = delta == null || delta === 0 ? 'var(--text-4)' : delta > 0 ? '#34d399' : '#f87171';
    return (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, padding: '18px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 30, height: 30, borderRadius: 8, background: `${color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Icon size={14} color={color} />
                    </div>
                    <span style={{ fontSize: 12, color: 'var(--text-4)', fontWeight: 600 }}>{label}</span>
                </div>
                {delta != null && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: 11.5, fontWeight: 700, color: deltaColor }}>
                        <DeltaIcon size={12} />{Math.abs(delta)}%
                    </span>
                )}
            </div>
            <div style={{ fontSize: 30, fontWeight: 800, lineHeight: 1 }}>{value}</div>
            {sub && <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6 }}>{sub}</div>}
        </div>
    );
}

function ChartCard({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
    return (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, padding: '20px 22px' }}>
            <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{title}</div>
            {sub && <div style={{ fontSize: 12, color: 'var(--text-4)', marginBottom: 12 }}>{sub}</div>}
            {children}
        </div>
    );
}

function tooltipStyle() {
    return { background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 8, fontSize: 12.5 };
}

function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { key: T; label: string }[]; onChange: (v: T) => void }) {
    return (
        <div style={{ display: 'flex', background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 8, overflow: 'hidden' }}>
            {options.map(o => (
                <button key={o.key} type="button" onClick={() => onChange(o.key)} style={{
                    padding: '7px 13px', border: 'none', cursor: 'pointer', fontSize: 12.5, fontWeight: 600,
                    background: value === o.key ? 'var(--primary)' : 'transparent',
                    color: value === o.key ? '#fff' : 'var(--text-2)',
                }}>{o.label}</button>
            ))}
        </div>
    );
}

function Select({ value, options, onChange }: { value: string; options: { value: string; label: string }[]; onChange: (v: string) => void }) {
    return (
        <select value={value} onChange={e => onChange(e.target.value)} style={{
            padding: '7px 12px', borderRadius: 8, border: '1px solid var(--border-default)',
            background: 'var(--bg-card)', color: 'var(--text-1)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
        }}>
            {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
    );
}

export default function AnalyticsPage() {
    const { accessToken, user, isLoading } = useAuth();
    const router = useRouter();
    const [leads, setLeads] = useState<Lead[]>([]);
    const [calls, setCalls] = useState<Call[]>([]);
    const [appts, setAppts] = useState<Appt[]>([]);
    const [convs, setConvs] = useState<Conv[]>([]);
    const [loading, setLoading] = useState(true);

    const [range, setRange] = useState<RangeKey>('30d');
    const [source, setSource] = useState('all');
    const [channel, setChannel] = useState('all');

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'analytics', 'admin')) {
            router.replace('/user/dashboard');
        }
    }, [isLoading, accessToken, user, router]);

    const load = () => {
        if (!accessToken) return;
        setLoading(true);
        const h = { Authorization: `Bearer ${accessToken}` };
        Promise.all([
            fetch(`/api/leads`, { headers: h }).then(r => r.json()),
            fetch('/api/crm/calls', { headers: h }).then(r => r.json()),
            fetch('/api/appointments?includeCancelled=true', { headers: h }).then(r => r.json()),
            fetch(`/api/conversations`, { headers: h }).then(r => r.json()),
        ]).then(([l, k, a, c]) => {
            setLeads(l?.data?.leads || []);
            setCalls(k?.data?.calls || []);
            setAppts(a?.data?.appointments || []);
            setConvs(c?.data?.conversations || []);
        }).catch(() => {}).finally(() => setLoading(false));
    };

    useEffect(() => { load(); }, [accessToken]); // eslint-disable-line react-hooks/exhaustive-deps

    const buckets = useMemo(() => buildBuckets(range), [range]);
    const rangeStart = buckets[0]?.start ?? new Date(0);
    const periodMs = Date.now() - rangeStart.getTime();
    const prevStart = new Date(rangeStart.getTime() - periodMs);

    const sourceOptions = useMemo(() => {
        const set = new Set(leads.map(l => l.source).filter(Boolean) as string[]);
        return ['all', ...Array.from(set)];
    }, [leads]);

    const inRange = (iso: string, start: Date, end: Date = new Date(8640000000000000)) => {
        const t = parseApiDate(iso).getTime();
        return t >= start.getTime() && t < end.getTime();
    };

    const leadsFiltered = useMemo(() => leads.filter(l =>
        inRange(l.created_at, rangeStart) && (source === 'all' || l.source === source)
    ), [leads, rangeStart, source]);

    const callsFiltered = useMemo(() => calls.filter(c => inRange(c.created_at, rangeStart)), [calls, rangeStart]);
    const apptsFiltered = useMemo(() => appts.filter(a => inRange(a.created_at, rangeStart)), [appts, rangeStart]);
    const convsFiltered = useMemo(() => convs.filter(c =>
        inRange(c.created_at, rangeStart) && (channel === 'all' || c.channel === channel)
    ), [convs, rangeStart, channel]);

    // Previous-period slices (for delta %) — same filters, shifted window
    const pctDelta = (curr: number, prevCount: number) => {
        if (prevCount === 0) return curr === 0 ? 0 : 100;
        return Math.round(((curr - prevCount) / prevCount) * 100);
    };
    const leadsPrevCount   = leads.filter(l => inRange(l.created_at, prevStart, rangeStart) && (source === 'all' || l.source === source)).length;
    const callsPrevCount   = calls.filter(c => inRange(c.created_at, prevStart, rangeStart)).length;
    const apptsPrevCount   = appts.filter(a => inRange(a.created_at, prevStart, rangeStart)).length;
    const convsPrevCount   = convs.filter(c => inRange(c.created_at, prevStart, rangeStart) && (channel === 'all' || c.channel === channel)).length;

    const trendData = buckets.map(b => ({
        label: b.label,
        leads: leadsFiltered.filter(l => inRange(l.created_at, b.start, b.end)).length,
        calls: callsFiltered.filter(c => inRange(c.created_at, b.start, b.end)).length,
        appointments: apptsFiltered.filter(a => inRange(a.created_at, b.start, b.end)).length,
    }));

    const stageSlices = STAGE_META.map(s => ({ ...s, value: leadsFiltered.filter(l => l.stage === s.key).length })).filter(s => s.value > 0);

    const funnelData = [
        { key: 'new_lead', label: 'New Lead' },
        { key: 'connected', label: 'Connected' },
        { key: 'quoted', label: 'Quoted' },
        { key: 'closed', label: 'Closed' },
    ].map((s, i) => ({
        name: s.label,
        value: leadsFiltered.filter(l => l.stage === s.key).length,
        fill: [PALETTE.indigo, PALETTE.sky, PALETTE.green, PALETTE.amber][i],
    }));

    const apptSlices = [
        { label: 'Confirmed', value: apptsFiltered.filter(a => a.status === 'confirmed').length, color: PALETTE.green },
        { label: 'Pending',   value: apptsFiltered.filter(a => a.status === 'pending').length,   color: PALETTE.amber },
        { label: 'Cancelled', value: apptsFiltered.filter(a => a.status === 'cancelled').length, color: PALETTE.red },
    ].filter(s => s.value > 0);

    const convChannels = [
        { label: 'SMS',      value: convsFiltered.filter(c => c.channel === 'sms').length,      color: PALETTE.indigo },
        { label: 'WhatsApp', value: convsFiltered.filter(c => c.channel === 'whatsapp').length,  color: PALETTE.green },
        { label: 'Voice',    value: convsFiltered.filter(c => c.channel === 'voice').length,     color: PALETTE.amber },
        { label: 'Chat',     value: convsFiltered.filter(c => c.channel === 'chat').length,      color: PALETTE.purple },
    ].filter(s => s.value > 0);

    const outcomeData = Object.entries(OUTCOME_META).map(([key, meta]) => ({
        label: meta.label, value: callsFiltered.filter(c => (c.outcome || '') === key).length, color: meta.color,
    })).filter(d => d.value > 0);

    const sourceData = useMemo(() => {
        const counts: Record<string, number> = {};
        leadsFiltered.forEach(l => { const s = l.source || 'unknown'; counts[s] = (counts[s] || 0) + 1; });
        return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, value]) => ({ label, value }));
    }, [leadsFiltered]);

    const totalCalls = callsFiltered.length;
    const avgDuration = callsFiltered.filter(c => c.duration_seconds).length > 0
        ? Math.round(callsFiltered.reduce((s, c) => s + (c.duration_seconds || 0), 0) / callsFiltered.filter(c => c.duration_seconds).length)
        : 0;
    const convRate = leadsFiltered.length > 0 ? Math.round((leadsFiltered.filter(l => l.stage === 'closed').length / leadsFiltered.length) * 100) : 0;
    const confirmedAppts = apptsFiltered.filter(a => a.status === 'confirmed').length;

    // ── Forecast: project the lead trend forward using a simple linear fit ──
    const FORECAST_STEPS = 3;
    const { slope: leadsSlope, forecast: leadsForecastVals } = useMemo(
        () => linearForecast(trendData.map(d => d.leads), FORECAST_STEPS),
        [trendData],
    );
    const forecastBuckets = useMemo(() => extendBucketsForward(range, FORECAST_STEPS), [range]);
    const chartData = useMemo(() => [
        ...trendData.map((d, i) => ({ ...d, leadsForecast: i === trendData.length - 1 ? d.leads : null })),
        ...forecastBuckets.map((b, i) => ({ label: b.label, leads: null, calls: null, appointments: null, leadsForecast: leadsForecastVals[i] })),
    ], [trendData, forecastBuckets, leadsForecastVals]);
    const projectedNextLeads = leadsForecastVals.reduce((a, b) => a + b, 0);

    // ── Risk & Attention: rule-based flags from the live (unfiltered by date range) data ──
    const DAY_MS = 86400000;
    const staleLeads = useMemo(() => leads
        .filter(l => source === 'all' || l.source === source)
        .filter(l => l.stage === 'connected' || l.stage === 'quoted')
        .map(l => ({ ...l, daysSince: Math.floor((Date.now() - parseApiDate(l.updated_at || l.created_at).getTime()) / DAY_MS) }))
        .filter(l => l.daysSince >= 7)
        .sort((a, b) => b.daysSince - a.daysSince), [leads, source]);

    const atRiskAppointments = useMemo(() => appts
        .filter(a => a.status === 'pending')
        .map(a => ({ ...a, hoursUntil: (parseApiDate(a.start_time || a.created_at).getTime() - Date.now()) / 3600000 }))
        .filter(a => a.hoursUntil >= 0 && a.hoursUntil <= 48)
        .sort((a, b) => a.hoursUntil - b.hoursUntil), [appts]);

    const unreachableLeads = useMemo(() => {
        const byPhone = new Map<string, Call[]>();
        calls.forEach(c => {
            if (!c.phone) return;
            if (!byPhone.has(c.phone)) byPhone.set(c.phone, []);
            byPhone.get(c.phone)!.push(c);
        });
        const out: { phone: string; name?: string; attempts: number }[] = [];
        byPhone.forEach((list, phone) => {
            const missed = list.filter(c => c.outcome === 'no_answer' || c.outcome === 'voicemail').length;
            const everConnected = list.some(c => c.outcome === 'confirmed' || c.outcome === 'info');
            if (missed >= 3 && !everConnected) out.push({ phone, name: list[0]?.patientName, attempts: missed });
        });
        return out.sort((a, b) => b.attempts - a.attempts);
    }, [calls]);

    type Risk = { severity: 'high' | 'medium' | 'low'; title: string; detail: string };
    const risks: Risk[] = useMemo(() => {
        const list: Risk[] = [
            ...staleLeads.slice(0, 5).map(l => ({
                severity: (l.daysSince >= 14 ? 'high' : 'medium') as Risk['severity'],
                title: `${[l.first_name, l.last_name].filter(Boolean).join(' ') || 'Lead'} stuck at ${STAGE_META.find(s => s.key === l.stage)?.label || l.stage}`,
                detail: `No stage movement in ${l.daysSince} days — follow up before this deal goes cold.`,
            })),
            ...atRiskAppointments.slice(0, 5).map(a => ({
                severity: (a.hoursUntil <= 12 ? 'high' : 'medium') as Risk['severity'],
                title: `${[a.first_name, a.last_name].filter(Boolean).join(' ') || 'Appointment'} unconfirmed`,
                detail: `Scheduled in ${Math.max(1, Math.round(a.hoursUntil))}h and still pending — confirm to avoid a no-show.`,
            })),
            ...unreachableLeads.slice(0, 5).map(u => ({
                severity: 'medium' as Risk['severity'],
                title: `${u.name || u.phone} unreachable`,
                detail: `${u.attempts} missed call attempts with no connection yet — try SMS instead of another call.`,
            })),
        ];
        const rank = { high: 0, medium: 1, low: 2 };
        return list.sort((a, b) => rank[a.severity] - rank[b.severity]).slice(0, 8);
    }, [staleLeads, atRiskAppointments, unreachableLeads]);

    // ── AI-style suggestions: deterministic insights derived from the same metrics above ──
    type Suggestion = { priority: 'High' | 'Medium' | 'Low'; text: string };
    const suggestions: Suggestion[] = useMemo(() => {
        const out: Suggestion[] = [];
        const missedCount = callsFiltered.filter(c => c.outcome === 'no_answer' || c.outcome === 'voicemail').length;
        const missedRate = totalCalls > 0 ? Math.round((missedCount / totalCalls) * 100) : 0;
        if (totalCalls >= 5 && missedRate >= 40) {
            out.push({ priority: 'High', text: `${missedRate}% of calls go unanswered — lead with an SMS before calling, or shift call times toward the best-performing slots below.` });
        }

        const bySource: Record<string, { total: number; closed: number }> = {};
        leadsFiltered.forEach(l => {
            const s = l.source || 'unknown';
            bySource[s] = bySource[s] || { total: 0, closed: 0 };
            bySource[s].total++;
            if (l.stage === 'closed') bySource[s].closed++;
        });
        const ranked = Object.entries(bySource).filter(([, v]) => v.total >= 2).map(([k, v]) => ({ source: k, rate: v.closed / v.total }));
        if (ranked.length >= 2) {
            ranked.sort((a, b) => b.rate - a.rate);
            const best = ranked[0], worst = ranked[ranked.length - 1];
            if (best.rate > worst.rate) {
                out.push({ priority: 'Medium', text: `Leads from "${best.source}" close at ${Math.round(best.rate * 100)}%, well above "${worst.source}" (${Math.round(worst.rate * 100)}%) — shift more effort toward ${best.source}.` });
            }
        }

        const funnelStages = STAGE_META.filter(s => ['new_lead', 'connected', 'quoted'].includes(s.key))
            .map(s => ({ ...s, count: leadsFiltered.filter(l => l.stage === s.key).length }));
        const top = [...funnelStages].sort((a, b) => b.count - a.count)[0];
        if (top && leadsFiltered.length > 0 && top.count >= 2 && top.count / leadsFiltered.length >= 0.4) {
            out.push({ priority: 'Medium', text: `${top.count} leads (${Math.round((top.count / leadsFiltered.length) * 100)}%) are sitting at "${top.label}" — that's your biggest bottleneck stage right now.` });
        }

        if (apptsFiltered.length >= 1) {
            const confirmRate = Math.round((confirmedAppts / apptsFiltered.length) * 100);
            if (confirmRate < 60) {
                out.push({ priority: 'Medium', text: `Only ${confirmRate}% of appointments are confirmed — add an automatic confirmation SMS 24h before each one.` });
            }
        }

        if (trendData.length >= 4) {
            if (leadsSlope < -0.05) {
                out.push({ priority: 'High', text: `Lead volume is trending down — projected ~${projectedNextLeads} over the next ${FORECAST_STEPS} periods. Consider a new acquisition channel or reactivating old leads.` });
            } else if (leadsSlope > 0.05) {
                out.push({ priority: 'Low', text: `Lead volume is trending up — projected ~${projectedNextLeads} over the next ${FORECAST_STEPS} periods. Make sure follow-up capacity can keep pace.` });
            }
        }

        if (out.length === 0) out.push({ priority: 'Low', text: 'No notable patterns detected yet in this view — check back once more activity accumulates.' });
        return out;
    }, [callsFiltered, totalCalls, leadsFiltered, apptsFiltered, confirmedAppts, trendData, leadsSlope, projectedNextLeads]);

    // ── Best time to call: weekday x time-of-day connect-rate heatmap ──
    const heatmap = useMemo(() => {
        const grid: Record<string, Record<string, { total: number; connected: number }>> = {};
        WEEKDAYS.forEach(d => { grid[d] = {}; TIME_SLOTS.forEach(s => { grid[d][s.key] = { total: 0, connected: 0 }; }); });
        callsFiltered.forEach(c => {
            const d = parseApiDate(c.created_at);
            const day = WEEKDAYS[d.getDay()];
            const slot = slotFor(d.getHours());
            grid[day][slot].total++;
            if (c.outcome === 'confirmed' || c.outcome === 'info') grid[day][slot].connected++;
        });
        return grid;
    }, [callsFiltered]);
    const maxHeatTotal = Math.max(1, ...WEEKDAYS.flatMap(d => TIME_SLOTS.map(s => heatmap[d][s.key].total)));

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <SideNav />
            <main style={{ marginLeft: 220, flex: 1, padding: 32, overflowY: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
                    <div>
                        <h1 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 4px' }}>Analytics</h1>
                        <p style={{ color: 'var(--text-4)', fontSize: 13 }}>Business performance overview</p>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        <Select value={source} onChange={setSource} options={sourceOptions.map(s => ({ value: s, label: s === 'all' ? 'All Sources' : s }))} />
                        <Select value={channel} onChange={setChannel} options={[
                            { value: 'all', label: 'All Channels' }, { value: 'sms', label: 'SMS' },
                            { value: 'whatsapp', label: 'WhatsApp' }, { value: 'voice', label: 'Voice' }, { value: 'chat', label: 'Chat' },
                        ]} />
                        <Segmented value={range} onChange={setRange} options={(Object.keys(RANGE_LABELS) as RangeKey[]).map(k => ({ key: k, label: RANGE_LABELS[k] }))} />
                        <button type="button" onClick={load} title="Refresh" style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 8,
                            border: '1px solid var(--border-default)', background: 'var(--bg-card)', cursor: 'pointer', color: 'var(--text-2)',
                        }}>
                            <RefreshCw size={14} style={loading ? { animation: 'spin 1s linear infinite' } : undefined} />
                        </button>
                    </div>
                </div>

                {loading ? <p style={{ color: 'var(--text-4)' }}>Loading...</p> : (<>

                {/* Top stats */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, marginBottom: 20 }}>
                    <StatCard label="Total Leads" value={leadsFiltered.length} icon={Users} color={PALETTE.indigo}
                        sub={`${convRate}% conversion`} delta={pctDelta(leadsFiltered.length, leadsPrevCount)} />
                    <StatCard label="Total Calls" value={totalCalls} icon={Phone} color={PALETTE.gold}
                        sub={avgDuration > 0 ? `Avg ${Math.floor(avgDuration / 60)}m ${avgDuration % 60}s` : 'No duration data'}
                        delta={pctDelta(totalCalls, callsPrevCount)} />
                    <StatCard label="Appointments" value={apptsFiltered.length} icon={CalendarDays} color={PALETTE.orange}
                        sub={`${confirmedAppts} confirmed`} delta={pctDelta(apptsFiltered.length, apptsPrevCount)} />
                    <StatCard label="Conversations" value={convsFiltered.length} icon={MessageCircle} color={PALETTE.purple}
                        sub={`${convsFiltered.filter(c => c.ai_active).length} AI active`} delta={pctDelta(convsFiltered.length, convsPrevCount)} />
                </div>

                {/* Trend chart + forecast */}
                <div style={{ marginBottom: 18 }}>
                    <ChartCard title="Activity Trend & Forecast" sub={`Leads, calls, appointments — ${RANGE_LABELS[range]}, with a ${FORECAST_STEPS}-period lead forecast (dashed)`}>
                        <ResponsiveContainer width="100%" height={260}>
                            <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="leadsFill" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor={PALETTE.indigo} stopOpacity={0.35} />
                                        <stop offset="95%" stopColor={PALETTE.indigo} stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-default)" vertical={false} />
                                <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--text-4)' }} axisLine={false} tickLine={false}
                                    interval={range === '30d' ? 3 : 0} />
                                <YAxis tick={{ fontSize: 10, fill: 'var(--text-4)' }} axisLine={false} tickLine={false} allowDecimals={false} />
                                <Tooltip contentStyle={tooltipStyle()} />
                                <Legend wrapperStyle={{ fontSize: 12 }} />
                                <Area type="monotone" dataKey="leads" name="Leads" stroke={PALETTE.indigo} fill="url(#leadsFill)" strokeWidth={2} connectNulls={false} />
                                <Bar dataKey="calls" name="Calls" fill={PALETTE.gold} radius={[3, 3, 0, 0]} barSize={range === '7d' ? 18 : 6} />
                                <Line type="monotone" dataKey="appointments" name="Appointments" stroke={PALETTE.green} strokeWidth={2} dot={false} connectNulls={false} />
                                <Line type="monotone" dataKey="leadsForecast" name="Leads (forecast)" stroke={PALETTE.indigo} strokeDasharray="5 5" strokeWidth={2} dot={false} connectNulls />
                            </ComposedChart>
                        </ResponsiveContainer>
                    </ChartCard>
                </div>

                {/* Funnel + Lead stage donut */}
                <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 18, marginBottom: 18 }}>
                    <ChartCard title="Lead Conversion Funnel" sub="New → Connected → Quoted → Closed">
                        {funnelData.every(f => f.value === 0) ? (
                            <p style={{ color: 'var(--text-4)', fontSize: 13 }}>No leads in this view</p>
                        ) : (
                            <ResponsiveContainer width="100%" height={220}>
                                <FunnelChart>
                                    <Tooltip contentStyle={tooltipStyle()} />
                                    <Funnel dataKey="value" data={funnelData} isAnimationActive>
                                        <LabelList position="right" dataKey="name" fill="var(--text-2)" stroke="none" fontSize={12} />
                                        <LabelList position="left" dataKey="value" fill="var(--text-1)" stroke="none" fontSize={13} fontWeight={700} />
                                    </Funnel>
                                </FunnelChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>

                    <ChartCard title="Lead Stage Breakdown" sub={`${leadsFiltered.length} total leads`}>
                        {stageSlices.length === 0 ? (
                            <p style={{ color: 'var(--text-4)', fontSize: 13 }}>No leads yet</p>
                        ) : (
                            <ResponsiveContainer width="100%" height={220}>
                                <PieChart>
                                    <Tooltip contentStyle={tooltipStyle()} />
                                    <Legend wrapperStyle={{ fontSize: 12 }} />
                                    <Pie data={stageSlices} dataKey="value" nameKey="label" innerRadius={45} outerRadius={75} paddingAngle={2}>
                                        {stageSlices.map((s, i) => <Cell key={i} fill={s.color} />)}
                                    </Pie>
                                </PieChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>
                </div>

                {/* Appointment status + Conversation channels */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, marginBottom: 18 }}>
                    <ChartCard title="Appointment Status" sub={`${apptsFiltered.length} total appointments`}>
                        {apptSlices.length === 0 ? (
                            <p style={{ color: 'var(--text-4)', fontSize: 13 }}>No appointments yet</p>
                        ) : (
                            <ResponsiveContainer width="100%" height={200}>
                                <PieChart>
                                    <Tooltip contentStyle={tooltipStyle()} />
                                    <Legend wrapperStyle={{ fontSize: 12 }} />
                                    <Pie data={apptSlices} dataKey="value" nameKey="label" innerRadius={42} outerRadius={70} paddingAngle={2}>
                                        {apptSlices.map((s, i) => <Cell key={i} fill={s.color} />)}
                                    </Pie>
                                </PieChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>

                    <ChartCard title="Conversation Channels" sub={`${convsFiltered.length} total conversations`}>
                        {convChannels.length === 0 ? (
                            <p style={{ color: 'var(--text-4)', fontSize: 13 }}>No conversations yet</p>
                        ) : (
                            <ResponsiveContainer width="100%" height={200}>
                                <PieChart>
                                    <Tooltip contentStyle={tooltipStyle()} />
                                    <Legend wrapperStyle={{ fontSize: 12 }} />
                                    <Pie data={convChannels} dataKey="value" nameKey="label" innerRadius={42} outerRadius={70} paddingAngle={2}>
                                        {convChannels.map((s, i) => <Cell key={i} fill={s.color} />)}
                                    </Pie>
                                </PieChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>
                </div>

                {/* Call outcomes + Lead sources */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
                    <ChartCard title="Call Outcomes" sub={`${totalCalls} total calls`}>
                        {outcomeData.length === 0 ? (
                            <p style={{ color: 'var(--text-4)', fontSize: 13 }}>No calls yet</p>
                        ) : (
                            <ResponsiveContainer width="100%" height={200}>
                                <BarChart data={outcomeData} layout="vertical" margin={{ left: 10 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-default)" horizontal={false} />
                                    <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--text-4)' }} axisLine={false} tickLine={false} allowDecimals={false} />
                                    <YAxis type="category" dataKey="label" tick={{ fontSize: 11, fill: 'var(--text-2)' }} axisLine={false} tickLine={false} width={90} />
                                    <Tooltip contentStyle={tooltipStyle()} />
                                    <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={16}>
                                        {outcomeData.map((d, i) => <Cell key={i} fill={d.color} />)}
                                    </Bar>
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>

                    <ChartCard title="Top Lead Sources" sub={`${leadsFiltered.length} total leads`}>
                        {sourceData.length === 0 ? (
                            <p style={{ color: 'var(--text-4)', fontSize: 13 }}>No leads yet</p>
                        ) : (
                            <ResponsiveContainer width="100%" height={200}>
                                <BarChart data={sourceData} layout="vertical" margin={{ left: 10 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-default)" horizontal={false} />
                                    <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--text-4)' }} axisLine={false} tickLine={false} allowDecimals={false} />
                                    <YAxis type="category" dataKey="label" tick={{ fontSize: 11, fill: 'var(--text-2)' }} axisLine={false} tickLine={false} width={90} />
                                    <Tooltip contentStyle={tooltipStyle()} />
                                    <Bar dataKey="value" fill={PALETTE.gold} radius={[0, 4, 4, 0]} barSize={16} />
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </ChartCard>
                </div>

                {/* Risk & Attention + AI Suggestions */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, marginTop: 18 }}>
                    <ChartCard title="Risk & Attention" sub="Deals and contacts that need a human look, ranked by urgency">
                        {risks.length === 0 ? (
                            <p style={{ color: 'var(--text-4)', fontSize: 13 }}>Nothing at risk right now.</p>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {risks.map((r, i) => {
                                    const color = r.severity === 'high' ? PALETTE.red : r.severity === 'medium' ? PALETTE.orange : PALETTE.slate;
                                    return (
                                        <div key={i} style={{ display: 'flex', gap: 10, padding: '10px 12px', borderRadius: 10, background: 'var(--surface-muted, rgba(0,0,0,0.02))', borderLeft: `3px solid ${color}` }}>
                                            <AlertTriangle size={15} color={color} style={{ flexShrink: 0, marginTop: 1 }} />
                                            <div>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>{r.title}</div>
                                                <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 2 }}>{r.detail}</div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </ChartCard>

                    <ChartCard title="AI-Suggested Actions" sub="Recommendations generated from the metrics on this page">
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {suggestions.map((s, i) => {
                                const color = s.priority === 'High' ? PALETTE.red : s.priority === 'Medium' ? PALETTE.orange : PALETTE.slate;
                                return (
                                    <div key={i} style={{ display: 'flex', gap: 10, padding: '10px 12px', borderRadius: 10, background: 'var(--surface-muted, rgba(0,0,0,0.02))', borderLeft: `3px solid ${color}` }}>
                                        <Lightbulb size={15} color={color} style={{ flexShrink: 0, marginTop: 1 }} />
                                        <div>
                                            <div style={{ fontSize: 10.5, fontWeight: 700, color, textTransform: 'uppercase', letterSpacing: 0.04 }}>{s.priority} priority</div>
                                            <div style={{ fontSize: 12.5, color: 'var(--text-2)', marginTop: 2, lineHeight: 1.5 }}>{s.text}</div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </ChartCard>
                </div>

                {/* Best time to call heatmap */}
                <div style={{ marginTop: 18 }}>
                    <ChartCard title="Best Time to Call" sub="Call volume and connect rate by day and time slot — darker = higher connect rate">
                        <div style={{ overflowX: 'auto' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: `70px repeat(${TIME_SLOTS.length}, 1fr)`, gap: 4, minWidth: 520 }}>
                                <div />
                                {TIME_SLOTS.map(s => (
                                    <div key={s.key} style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--text-4)', textAlign: 'center', paddingBottom: 4 }}>{s.label}</div>
                                ))}
                                {WEEKDAYS.map(day => (
                                    <Fragment key={day}>
                                        <div style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-2)', display: 'flex', alignItems: 'center' }}>{day}</div>
                                        {TIME_SLOTS.map(slot => {
                                            const cell = heatmap[day][slot.key];
                                            const rate = cell.total > 0 ? cell.connected / cell.total : 0;
                                            const opacity = cell.total === 0 ? 0.06 : 0.18 + (cell.total / maxHeatTotal) * 0.35 + rate * 0.35;
                                            return (
                                                <div key={`${day}-${slot.key}`} title={`${cell.total} calls, ${Math.round(rate * 100)}% connected`}
                                                    style={{
                                                        borderRadius: 8, padding: '10px 4px', textAlign: 'center',
                                                        background: cell.total === 0 ? 'var(--border-default)' : PALETTE.green,
                                                        opacity: cell.total === 0 ? 0.4 : Math.min(1, opacity),
                                                    }}>
                                                    <div style={{ fontSize: 13, fontWeight: 800, color: cell.total === 0 ? 'var(--text-4)' : '#0a2e1f' }}>{cell.total || '—'}</div>
                                                    {cell.total > 0 && <div style={{ fontSize: 9.5, color: '#0a2e1f', opacity: 0.85 }}>{Math.round(rate * 100)}% connect</div>}
                                                </div>
                                            );
                                        })}
                                    </Fragment>
                                ))}
                            </div>
                        </div>
                    </ChartCard>
                </div>

                </>)}
            </main>
        </div>
    );
}
