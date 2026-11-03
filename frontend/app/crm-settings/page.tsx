'use client';

import { useCallback, useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import {
    Settings2, Save, Clock, Calendar, Play, Pause, Zap,
    CheckCircle2, AlertCircle, Smartphone, Radio, Globe, ShieldCheck
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { hasModuleAccess } from '@/lib/permissions';
import styles from './crm-settings.module.css';

type Tab = 'campaign' | 'communication' | 'statuses' | 'assignment' | 'scoring' | 'pipeline';

interface Stage {
    id: string; key: string; label: string; color: string; sort_order: number;
    is_closed_won: boolean; is_closed_lost: boolean;
}
interface ScoringRule { id: string; factor_key: string; weight: number; enabled: boolean; }
interface StaffUser { id: string; firstName?: string; lastName?: string; email: string; role: string; }

const FACTOR_LABELS: Record<string, string> = {
    sms_engagement: 'SMS Engagement',
    call_engagement: 'Call Duration / Engagement',
    appointment_activity: 'Appointment Attendance',
    quote_requests: 'Quote Requests',
    ai_sentiment: 'AI Sentiment Analysis',
};

const DAYS = [
    { key: 'mon', label: 'Mon' },
    { key: 'tue', label: 'Tue' },
    { key: 'wed', label: 'Wed' },
    { key: 'thu', label: 'Thu' },
    { key: 'fri', label: 'Fri' },
    { key: 'sat', label: 'Sat' },
    { key: 'sun', label: 'Sun' },
];

const TIMEZONES = [
    { val: 'America/New_York', label: 'Eastern Time (EST / EDT) — New York / Troy' },
    { val: 'America/Chicago', label: 'Central Time (CST / CDT) — Chicago / Texas' },
    { val: 'America/Denver', label: 'Mountain Time (MST / MDT) — Denver' },
    { val: 'America/Los_Angeles', label: 'Pacific Time (PST / PDT) — California' },
    { val: 'Asia/Karachi', label: 'Pakistan Standard Time (PKT) — Karachi' },
    { val: 'UTC', label: 'UTC (Coordinated Universal Time)' },
];

export default function CrmSettingsPage() {
    const { accessToken, isLoading, user } = useAuth();
    const router = useRouter();
    const [tab, setTab] = useState<Tab>('campaign');
    const [saved, setSaved] = useState(false);

    const [stages, setStages] = useState<Stage[]>([]);
    const [assignmentMode, setAssignmentMode] = useState('manual');
    const [assignmentUserIds, setAssignmentUserIds] = useState<string[]>([]);
    const [staff, setStaff] = useState<StaffUser[]>([]);
    const [scoringRules, setScoringRules] = useState<ScoringRule[]>([]);
    const [commRules, setCommRules] = useState({
        quiet_hours_start: '09:00',
        quiet_hours_end: '20:00',
        timezone: 'America/New_York',
        max_sms_per_day: 5,
        max_calls_per_day: 3,
        channels_enabled: { sms: true, whatsapp: true, call: true, email: false } as Record<string, boolean>,
        campaign_start_time: '09:00',
        campaign_end_time: '18:00',
        campaign_days: ['mon', 'tue', 'wed', 'thu', 'fri'] as string[],
        campaign_active: true,
        campaign_daily_limit: 50,
    });

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'crm_settings', 'admin')) router.replace('/leads');
    }, [isLoading, accessToken, user, router]);

    const h = useCallback(() => ({ Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' }), [accessToken]);

    const load = useCallback(async () => {
        if (!accessToken) return;
        const headers = { Authorization: `Bearer ${accessToken}` };
        try {
            const [stagesRes, assignRes, scoreRes, commRes, staffRes] = await Promise.all([
                fetch('/api/crm-settings/stages', { headers }).then(r => r.json()),
                fetch('/api/crm-settings/assignment-rules', { headers }).then(r => r.json()),
                fetch('/api/crm-settings/scoring-rules', { headers }).then(r => r.json()),
                fetch('/api/crm-settings/communication-rules', { headers }).then(r => r.json()),
                fetch('/api/admin/users', { headers }).then(r => r.json()).catch(() => null),
            ]);
            if (stagesRes.success) setStages(stagesRes.data.stages);
            if (assignRes.success) {
                setAssignmentMode(assignRes.data.rule.mode);
                setAssignmentUserIds(assignRes.data.rule.config?.user_ids || []);
            }
            if (scoreRes.success) setScoringRules(scoreRes.data.rules);
            if (commRes.success && commRes.data?.rule) {
                setCommRules(prev => ({
                    ...prev,
                    ...commRes.data.rule,
                    campaign_start_time: commRes.data.rule.campaign_start_time || '09:00',
                    campaign_end_time: commRes.data.rule.campaign_end_time || '18:00',
                    campaign_days: commRes.data.rule.campaign_days || ['mon', 'tue', 'wed', 'thu', 'fri'],
                    campaign_active: commRes.data.rule.campaign_active !== undefined ? commRes.data.rule.campaign_active : true,
                    campaign_daily_limit: commRes.data.rule.campaign_daily_limit || 50,
                }));
            }
            if (staffRes?.success) setStaff(staffRes.data.users || staffRes.data || []);
        } catch (e) {
            console.error('Failed to load CRM settings:', e);
        }
    }, [accessToken]);

    useEffect(() => { load(); }, [load]);

    const flash = () => { setSaved(true); setTimeout(() => setSaved(false), 2500); };

    const saveStages = async () => {
        await fetch('/api/crm-settings/stages', { method: 'PUT', headers: h(), body: JSON.stringify(stages) });
        flash();
    };

    const saveAssignment = async () => {
        await fetch('/api/crm-settings/assignment-rules', {
            method: 'PUT', headers: h(),
            body: JSON.stringify({ mode: assignmentMode, config: { user_ids: assignmentUserIds } }),
        });
        flash();
    };

    const saveScoring = async () => {
        await fetch('/api/crm-settings/scoring-rules', { method: 'PUT', headers: h(), body: JSON.stringify(scoringRules) });
        flash();
    };

    const saveComm = async () => {
        await fetch('/api/crm-settings/communication-rules', { method: 'PUT', headers: h(), body: JSON.stringify(commRules) });
        flash();
    };

    const updateStage = (idx: number, patch: Partial<Stage>) =>
        setStages(s => s.map((st, i) => i === idx ? { ...st, ...patch } : st));

    const toggleAssignmentUser = (id: string) =>
        setAssignmentUserIds(ids => ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id]);

    const updateWeight = (factorKey: string, weight: number) =>
        setScoringRules(rs => rs.map(r => r.factor_key === factorKey ? { ...r, weight } : r));

    const toggleFactorEnabled = (factorKey: string) =>
        setScoringRules(rs => rs.map(r => r.factor_key === factorKey ? { ...r, enabled: !r.enabled } : r));

    const toggleDay = (dayKey: string) => {
        setCommRules(c => {
            const current = c.campaign_days || [];
            const updated = current.includes(dayKey)
                ? current.filter(d => d !== dayKey)
                : [...current, dayKey];
            return { ...c, campaign_days: updated };
        });
    };

    // Calculate real-time campaign status based on current time in selected timezone
    const campaignStatus = useMemo(() => {
        if (!commRules.campaign_active) {
            return { active: false, badgeClass: styles.statusPulseDotDisabled, title: 'Outreach Paused', desc: 'Campaign sending is disabled in CRM Settings.' };
        }
        try {
            const now = new Date();
            const tz = commRules.timezone || 'America/New_York';
            const options: Intl.DateTimeFormatOptions = { timeZone: tz, hour12: false, hour: '2-digit', minute: '2-digit', weekday: 'short' };
            const formatter = new Intl.DateTimeFormat('en-US', options);
            const parts = formatter.formatToParts(now);
            const hour = parseInt(parts.find(p => p.type === 'hour')?.value || '0', 10);
            const minute = parseInt(parts.find(p => p.type === 'minute')?.value || '0', 10);
            const weekday = (parts.find(p => p.type === 'weekday')?.value || '').toLowerCase().slice(0, 3);

            const currentMinutes = hour * 60 + minute;
            const [sh, sm] = (commRules.campaign_start_time || '09:00').split(':').map(Number);
            const [eh, em] = (commRules.campaign_end_time || '18:00').split(':').map(Number);
            const startMinutes = sh * 60 + sm;
            const endMinutes = eh * 60 + em;

            const activeDays = commRules.campaign_days || ['mon', 'tue', 'wed', 'thu', 'fri'];
            const timeFormatted = `${hour > 12 ? hour - 12 : hour || 12}:${minute < 10 ? '0' + minute : minute} ${hour >= 12 ? 'PM' : 'AM'}`;

            if (!activeDays.includes(weekday)) {
                return {
                    active: false,
                    badgeClass: styles.statusPulseDotInactive,
                    title: 'Outside Active Days',
                    desc: `Today is ${weekday.toUpperCase()} (Target office time: ${timeFormatted}). Scheduled active days: ${activeDays.map(d => d.toUpperCase()).join(', ')}.`
                };
            }

            if (currentMinutes >= startMinutes && currentMinutes <= endMinutes) {
                return {
                    active: true,
                    badgeClass: styles.statusPulseDot,
                    title: 'Active (Within Outreach Hours)',
                    desc: `Currently sending during business hours: ${commRules.campaign_start_time} - ${commRules.campaign_end_time} (${timeFormatted} ${tz}).`
                };
            } else if (currentMinutes < startMinutes) {
                return {
                    active: false,
                    badgeClass: styles.statusPulseDotInactive,
                    title: 'Outside Campaign Hours',
                    desc: `Currently ${timeFormatted} in ${tz}. Outreach auto-starts at ${commRules.campaign_start_time}.`
                };
            } else {
                return {
                    active: false,
                    badgeClass: styles.statusPulseDotInactive,
                    title: 'Outside Campaign Hours',
                    desc: `Currently ${timeFormatted} in ${tz}. Paused for the evening; auto-resumes at ${commRules.campaign_start_time} tomorrow.`
                };
            }
        } catch (e) {
            return { active: true, badgeClass: styles.statusPulseDot, title: 'Active', desc: 'Campaign schedule active.' };
        }
    }, [commRules]);

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>
                <div className={styles.header}>
                    <div className={styles.headerIcon}><Settings2 size={22} /></div>
                    <div className={styles.headerInfo}>
                        <h1>CRM & Campaign Settings</h1>
                        <p>Configure automated outreach schedules, active business hours (e.g. 9:00 AM – 6:00 PM), gateway controls, and communication limits.</p>
                    </div>
                </div>

                <div className={styles.tabRail}>
                    {(['campaign', 'communication', 'statuses', 'assignment', 'scoring'] as Tab[]).map(t => (
                        <button key={t} className={`${styles.tab} ${tab === t ? styles.tabActive : ''}`} onClick={() => setTab(t)}>
                            {t === 'campaign' ? '⏰ Campaign Schedule & Hours' :
                             t === 'communication' ? 'Communication Rules' :
                             t === 'statuses' ? 'Lead Statuses' :
                             t === 'assignment' ? 'Assignment Rules' : 'Lead Scoring'}
                        </button>
                    ))}
                </div>

                {/* ── TAB 1: CAMPAIGN SCHEDULE & HOURS ── */}
                {tab === 'campaign' && (
                    <div className={styles.panel}>
                        {/* Live Status Hero Card */}
                        <div className={styles.heroStatusCard}>
                            <div className={styles.heroStatusLeft}>
                                <div className={campaignStatus.badgeClass} />
                                <div>
                                    <div className={styles.statusTitle}>
                                        {campaignStatus.title}
                                        {commRules.campaign_active ? (
                                            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: 'rgba(16, 185, 129, 0.15)', color: '#047857', fontWeight: 700 }}>
                                                ONLINE
                                            </span>
                                        ) : (
                                            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: 'rgba(239, 68, 68, 0.15)', color: '#B91C1C', fontWeight: 700 }}>
                                                PAUSED
                                            </span>
                                        )}
                                    </div>
                                    <div className={styles.statusSubtitle}>{campaignStatus.desc}</div>
                                </div>
                            </div>
                            <div>
                                <button
                                    type="button"
                                    onClick={() => setCommRules(c => ({ ...c, campaign_active: !c.campaign_active }))}
                                    style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: 6,
                                        padding: '7px 14px',
                                        borderRadius: 8,
                                        fontSize: 12.5,
                                        fontWeight: 700,
                                        cursor: 'pointer',
                                        border: '1px solid',
                                        background: commRules.campaign_active ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.15)',
                                        borderColor: commRules.campaign_active ? '#EF4444' : '#10B981',
                                        color: commRules.campaign_active ? '#DC2626' : '#047857'
                                    }}
                                >
                                    {commRules.campaign_active ? <Pause size={14} /> : <Play size={14} />}
                                    {commRules.campaign_active ? 'Pause Campaign' : 'Enable Campaign'}
                                </button>
                            </div>
                        </div>

                        {/* Schedule Time Window Section */}
                        <div className={styles.scheduleSection}>
                            <div className={styles.sectionHeading}>
                                <Clock size={16} color="var(--primary)" />
                                <span>Daily Operational Window (Start & End Time)</span>
                            </div>
                            <p style={{ fontSize: 12, color: 'var(--text-3)', margin: 0 }}>
                                The campaign pacer will strictly only dispatch outreach between these hours. If an interaction falls outside this window, it will pause and resume the next business morning.
                            </p>

                            <div className={styles.grid2}>
                                <div className={styles.field}>
                                    <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>Start Time (Morning)</label>
                                    <input
                                        type="time"
                                        value={commRules.campaign_start_time || '09:00'}
                                        onChange={e => setCommRules(c => ({ ...c, campaign_start_time: e.target.value }))}
                                        style={{ fontSize: 14, fontWeight: 700, padding: '8px 12px' }}
                                    />
                                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>Default: 09:00 AM</span>
                                </div>
                                <div className={styles.field}>
                                    <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>End Time (Evening)</label>
                                    <input
                                        type="time"
                                        value={commRules.campaign_end_time || '18:00'}
                                        onChange={e => setCommRules(c => ({ ...c, campaign_end_time: e.target.value }))}
                                        style={{ fontSize: 14, fontWeight: 700, padding: '8px 12px' }}
                                    />
                                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>Default: 06:00 PM (18:00)</span>
                                </div>
                            </div>

                            {/* Quick Presets Bar */}
                            <div>
                                <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-3)' }}>Quick Hour Presets:</span>
                                <div className={styles.presetBar}>
                                    <button
                                        type="button"
                                        className={styles.presetBtn}
                                        onClick={() => setCommRules(c => ({ ...c, campaign_start_time: '09:00', campaign_end_time: '18:00' }))}
                                    >
                                        ⭐ 9:00 AM – 6:00 PM (Full Day)
                                    </button>
                                    <button
                                        type="button"
                                        className={styles.presetBtn}
                                        onClick={() => setCommRules(c => ({ ...c, campaign_start_time: '09:00', campaign_end_time: '17:30' }))}
                                    >
                                        🏢 9:00 AM – 5:30 PM (Office Hours)
                                    </button>
                                    <button
                                        type="button"
                                        className={styles.presetBtn}
                                        onClick={() => setCommRules(c => ({ ...c, campaign_start_time: '10:00', campaign_end_time: '19:00' }))}
                                    >
                                        🌆 10:00 AM – 7:00 PM (Late Schedule)
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Timezone Selector Section */}
                        <div className={styles.scheduleSection}>
                            <div className={styles.sectionHeading}>
                                <Globe size={16} color="var(--primary)" />
                                <span>Target Campaign Timezone</span>
                            </div>
                            <div className={styles.field}>
                                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)' }}>Operational Timezone</label>
                                <select
                                    value={commRules.timezone || 'America/New_York'}
                                    onChange={e => setCommRules(c => ({ ...c, timezone: e.target.value }))}
                                    style={{
                                        padding: '10px 14px',
                                        borderRadius: 8,
                                        border: '1px solid var(--border-default)',
                                        background: 'var(--bg-surface)',
                                        color: 'var(--text-1)',
                                        fontSize: 13,
                                        fontWeight: 600
                                    }}
                                >
                                    {TIMEZONES.map(tz => (
                                        <option key={tz.val} value={tz.val}>{tz.label}</option>
                                    ))}
                                </select>
                                <span style={{ fontSize: 11, color: 'var(--text-4)' }}>
                                    Campaign hours are calculated against this geographic region (Eastern Time for Troy Farmers Campaign).
                                </span>
                            </div>
                        </div>

                        {/* Active Days Selector */}
                        <div className={styles.scheduleSection}>
                            <div className={styles.sectionHeading}>
                                <Calendar size={16} color="var(--primary)" />
                                <span>Active Campaign Days</span>
                            </div>
                            <div className={styles.daysGrid}>
                                {DAYS.map(d => {
                                    const active = (commRules.campaign_days || []).includes(d.key);
                                    return (
                                        <button
                                            key={d.key}
                                            type="button"
                                            className={`${styles.dayBtn} ${active ? styles.dayBtnActive : ''}`}
                                            onClick={() => toggleDay(d.key)}
                                        >
                                            {active ? '✓ ' : ''}{d.label}
                                        </button>
                                    );
                                })}
                            </div>
                            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                                <button
                                    type="button"
                                    className={styles.presetBtn}
                                    onClick={() => setCommRules(c => ({ ...c, campaign_days: ['mon', 'tue', 'wed', 'thu', 'fri'] }))}
                                >
                                    Mon – Fri (Weekdays Only)
                                </button>
                                <button
                                    type="button"
                                    className={styles.presetBtn}
                                    onClick={() => setCommRules(c => ({ ...c, campaign_days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'] }))}
                                >
                                    Mon – Sat (6 Days)
                                </button>
                                <button
                                    type="button"
                                    className={styles.presetBtn}
                                    onClick={() => setCommRules(c => ({ ...c, campaign_days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] }))}
                                >
                                    All 7 Days
                                </button>
                            </div>
                        </div>

                        {/* Volume Limits & Velocity */}
                        <div className={styles.scheduleSection}>
                            <div className={styles.sectionHeading}>
                                <Zap size={16} color="var(--primary)" />
                                <span>Velocity & Daily Dispatch Limits</span>
                            </div>
                            <div className={styles.grid2}>
                                <div className={styles.field}>
                                    <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>Daily Max Campaign Messages</label>
                                    <input
                                        type="number"
                                        min={1}
                                        max={500}
                                        value={commRules.campaign_daily_limit || 50}
                                        onChange={e => setCommRules(c => ({ ...c, campaign_daily_limit: Number(e.target.value) }))}
                                        style={{ fontSize: 14, fontWeight: 700, padding: '8px 12px' }}
                                    />
                                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>Recommended: 50 – 80 messages / day per SIM card.</span>
                                </div>
                                <div className={styles.field}>
                                    <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>Human Cadence Pacing</label>
                                    <div style={{ padding: '9px 12px', background: 'var(--bg-surface)', border: '1px solid var(--border-default)', borderRadius: 8, fontSize: 13, fontWeight: 600, color: 'var(--text-2)' }}>
                                        45s – 120s randomized human delay
                                    </div>
                                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>Simulates human typing & prevents carrier spam flagging.</span>
                                </div>
                            </div>
                        </div>

                        {/* Active Cellular Gateway Box */}
                        <div style={{ padding: '14px 18px', borderRadius: 10, background: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.25)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <Smartphone size={20} color="#059669" />
                                <div>
                                    <div style={{ fontSize: 13, fontWeight: 700, color: '#065F46' }}>Connected Gateway: Android POCO123 (TextBee)</div>
                                    <div style={{ fontSize: 11.5, color: '#047857' }}>Dual-SIM Active • Jazz SIM 1 & SIM 2 Ready • 100% Cellular Delivery</div>
                                </div>
                            </div>
                            <div className={styles.simBadge}>
                                <Radio size={12} color="#059669" />
                                <span>Full Signal (4/4)</span>
                            </div>
                        </div>

                        {/* Save Action */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
                            <button className={styles.btnPrimary} onClick={saveComm} style={{ padding: '10px 20px', fontSize: 14 }}>
                                <Save size={15} /> Save Campaign Settings
                            </button>
                            {saved && <span className={styles.savedNote} style={{ fontSize: 13, fontWeight: 700 }}>✓ Campaign Settings Saved Successfully!</span>}
                        </div>
                    </div>
                )}

                {/* ── TAB 2: COMMUNICATION RULES ── */}
                {tab === 'communication' && (
                    <div className={styles.panel}>
                        <div className={styles.grid2}>
                            <div className={styles.field}>
                                <label>Quiet hours start</label>
                                <input type="time" value={commRules.quiet_hours_start}
                                    onChange={e => setCommRules(c => ({ ...c, quiet_hours_start: e.target.value }))} />
                            </div>
                            <div className={styles.field}>
                                <label>Quiet hours end</label>
                                <input type="time" value={commRules.quiet_hours_end}
                                    onChange={e => setCommRules(c => ({ ...c, quiet_hours_end: e.target.value }))} />
                            </div>
                            <div className={styles.field}>
                                <label>Max SMS / day / lead</label>
                                <input type="number" min={0} value={commRules.max_sms_per_day}
                                    onChange={e => setCommRules(c => ({ ...c, max_sms_per_day: Number(e.target.value) }))} />
                            </div>
                            <div className={styles.field}>
                                <label>Max calls / day / lead</label>
                                <input type="number" min={0} value={commRules.max_calls_per_day}
                                    onChange={e => setCommRules(c => ({ ...c, max_calls_per_day: Number(e.target.value) }))} />
                            </div>
                        </div>
                        <div className={styles.field}>
                            <label>Channels enabled</label>
                            <div style={{ display: 'flex', gap: 16 }}>
                                {Object.keys(commRules.channels_enabled).map(ch => (
                                    <label key={ch} className={styles.staffCheckItem}>
                                        <input type="checkbox" checked={commRules.channels_enabled[ch]}
                                            onChange={() => setCommRules(c => ({ ...c, channels_enabled: { ...c.channels_enabled, [ch]: !c.channels_enabled[ch] } }))} />
                                        {ch}
                                    </label>
                                ))}
                            </div>
                        </div>
                        <button className={styles.btnPrimary} onClick={saveComm}><Save size={13} /> Save Communication Rules</button>
                        {saved && <span className={styles.savedNote}>✓ Saved</span>}
                    </div>
                )}

                {/* ── TAB 3: STATUSES ── */}
                {tab === 'statuses' && (
                    <div className={styles.panel}>
                        {stages.map((s, i) => (
                            <div key={s.key} className={styles.stageRow}>
                                <input type="color" className={styles.colorDot} value={s.color}
                                    onChange={e => updateStage(i, { color: e.target.value })} style={{ padding: 0, cursor: 'pointer' }} />
                                <input className={styles.stageLabel} value={s.label} onChange={e => updateStage(i, { label: e.target.value })} />
                                <span style={{ fontSize: 11, color: 'var(--text-4)' }}>{s.key}</span>
                            </div>
                        ))}
                        <button className={styles.btnPrimary} onClick={saveStages}><Save size={13} /> Save Statuses</button>
                        {saved && <span className={styles.savedNote}>✓ Saved</span>}
                    </div>
                )}

                {/* ── TAB 4: ASSIGNMENT ── */}
                {tab === 'assignment' && (
                    <div className={styles.panel}>
                        <div className={styles.row}>
                            <span style={{ fontSize: 13, fontWeight: 600 }}>Assignment Mode:</span>
                            {['manual', 'round_robin', 'territory_based'].map(m => (
                                <button key={m}
                                    className={`${styles.modeOption} ${assignmentMode === m ? styles.modeOptionActive : ''}`}
                                    onClick={() => setAssignmentMode(m)}>
                                    {m === 'manual' ? 'Manual' : m === 'round_robin' ? 'Round Robin' : 'Territory Based'}
                                </button>
                            ))}
                        </div>

                        {assignmentMode === 'round_robin' && (
                            <div className={styles.field}>
                                <label>Included Staff Members</label>
                                <div className={styles.staffCheckList}>
                                    {staff.map(u => (
                                        <label key={u.id} className={styles.staffCheckItem}>
                                            <input type="checkbox" checked={assignmentUserIds.includes(u.id)}
                                                onChange={() => toggleAssignmentUser(u.id)} />
                                            {u.firstName || ''} {u.lastName || ''} ({u.email})
                                        </label>
                                    ))}
                                    {staff.length === 0 && <span style={{ fontSize: 12, color: 'var(--text-4)' }}>No staff found.</span>}
                                </div>
                            </div>
                        )}

                        {assignmentMode === 'territory_based' && (
                            <p style={{ fontSize: 12.5, color: 'var(--text-3)' }}>
                                Territory rules (tag/source-based routing to a specific staff member) are configured via the API
                                for now — a visual rule builder is planned for a future pass.
                            </p>
                        )}

                        <button className={styles.btnPrimary} onClick={saveAssignment}><Save size={13} /> Save Assignment Rules</button>
                        {saved && <span className={styles.savedNote}>✓ Saved</span>}
                    </div>
                )}

                {/* ── TAB 5: SCORING ── */}
                {tab === 'scoring' && (
                    <div className={styles.panel}>
                        {scoringRules.map(r => (
                            <div key={r.factor_key} className={styles.scoreRow}>
                                <input type="checkbox" checked={r.enabled} onChange={() => toggleFactorEnabled(r.factor_key)} />
                                <span className={styles.scoreLabel}>{FACTOR_LABELS[r.factor_key] || r.factor_key}</span>
                                <input type="number" min={0} max={100} className={styles.scoreWeight}
                                    value={r.weight} onChange={e => updateWeight(r.factor_key, Number(e.target.value))} />
                                <span style={{ fontSize: 11, color: 'var(--text-4)' }}>max points</span>
                            </div>
                        ))}
                        <button className={styles.btnPrimary} onClick={saveScoring}><Save size={13} /> Save Scoring Weights</button>
                        {saved && <span className={styles.savedNote}>✓ Saved</span>}
                    </div>
                )}
            </div>
        </div>
    );
}
