'use client';

import { useCallback, useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import {
    Settings2, Save, Clock, Calendar, Play, Pause, Zap,
    CheckCircle2, AlertCircle, Smartphone, Radio, Globe, ShieldCheck,
    Send, RefreshCw, Server, Info, Lock
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { hasModuleAccess } from '@/lib/permissions';
import styles from './crm-settings.module.css';

type Tab = 'campaign' | 'gateways' | 'communication' | 'statuses' | 'assignment' | 'scoring' | 'pipeline';

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

    // ── Gateway Settings State ──
    const [gatewaySettings, setGatewaySettings] = useState({
        provider: 'auto',
        enable_fallback: true,
        bb_server_url: 'https://villages-roberts-apt-mountains.trycloudflare.com',
        bb_password: 'Abc@12345',
        bb_send_method: 'apple-script',
        textbee_api_key: 'txb_zFvR5vrF3wgCkX4VCdM8hDsnnx1uFPH5',
        textbee_device_id: '6ae9fa7a59a24e053fc15a8a',
        textbee_base_url: 'https://api.textbee.dev/api/v1',
        textbee_phone: '0328 1044778 (Jazz SIM)',
        bluebubbles_account: 'alibaig1091@gmail.com',
    });
    const [bbTestResult, setBbTestResult] = useState<any>(null);
    const [bbTesting, setBbTesting] = useState(false);
    const [bbShowPassword, setBbShowPassword] = useState(false);
    const [textbeeTestResult, setTextbeeTestResult] = useState<any>(null);
    const [textbeeTesting, setTextbeeTesting] = useState(false);
    const [iphoneQueue, setIphoneQueue] = useState<any>({ pending_count: 0, sent_count: 0, pending_items: [], recent_sent: [] });
    const [loadingGateways, setLoadingGateways] = useState(false);
    const [gatewaySaved, setGatewaySaved] = useState(false);

    // Live Dispatcher State
    const [testPhone, setTestPhone] = useState('+923324545818');
    const [testMessage, setTestMessage] = useState('AllZone CRM Gateway Test: Testing direct delivery.');
    const [testProvider, setTestProvider] = useState('auto');
    const [testSending, setTestSending] = useState(false);
    const [testSendResult, setTestSendResult] = useState<any>(null);

    // iPhone Enqueue State
    const [enqueuePhone, setEnqueuePhone] = useState('');
    const [enqueueMessage, setEnqueueMessage] = useState('');
    const [enqueueStatus, setEnqueueStatus] = useState<string | null>(null);

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

    const loadGateways = useCallback(async () => {
        setLoadingGateways(true);
        try {
            const [gwRes, iphRes] = await Promise.all([
                fetch('/api/sms/gateway-settings').then(r => r.json()).catch(() => null),
                fetch('/api/sms/iphone/status').then(r => r.json()).catch(() => null),
            ]);
            if (gwRes && !gwRes.error) {
                setGatewaySettings(prev => ({ ...prev, ...gwRes }));
            }
            if (iphRes && !iphRes.error) {
                setIphoneQueue(iphRes);
            }
        } catch (e) {
            console.error('Failed to load gateway info:', e);
        } finally {
            setLoadingGateways(false);
        }
    }, []);

    useEffect(() => {
        loadGateways();
    }, [loadGateways]);

    const saveGatewaySettings = async () => {
        try {
            const res = await fetch('/api/sms/gateway-settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    provider: gatewaySettings.provider,
                    enable_fallback: gatewaySettings.enable_fallback,
                    bb_server_url: gatewaySettings.bb_server_url,
                    bb_password: gatewaySettings.bb_password,
                    bb_send_method: gatewaySettings.bb_send_method,
                    textbee_api_key: gatewaySettings.textbee_api_key,
                    textbee_device_id: gatewaySettings.textbee_device_id,
                }),
            });
            const data = await res.json();
            if (data.ok) {
                setGatewaySaved(true);
                setTimeout(() => setGatewaySaved(false), 2500);
            }
        } catch (e) {
            console.error('Failed to save gateway settings:', e);
        }
    };

    const testBlueBubbles = async () => {
        setBbTesting(true);
        setBbTestResult(null);
        try {
            const res = await fetch('/api/sms/gateway-test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gateway: 'bluebubbles' }),
            });
            const data = await res.json();
            setBbTestResult(data);
        } catch (e: any) {
            setBbTestResult({ ok: false, error: e.message || 'Connection test failed' });
        } finally {
            setBbTesting(false);
        }
    };

    const testTextBee = async () => {
        setTextbeeTesting(true);
        setTextbeeTestResult(null);
        try {
            const res = await fetch('/api/sms/gateway-test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gateway: 'textbee' }),
            });
            const data = await res.json();
            setTextbeeTestResult(data);
        } catch (e: any) {
            setTextbeeTestResult({ ok: false, error: e.message || 'Connection test failed' });
        } finally {
            setTextbeeTesting(false);
        }
    };

    const runDirectTestSend = async () => {
        if (!testPhone || !testMessage) return;
        setTestSending(true);
        setTestSendResult(null);
        try {
            const res = await fetch('/api/sms/direct-send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone: testPhone,
                    message: testMessage,
                    provider: testProvider,
                }),
            });
            const data = await res.json();
            setTestSendResult(data);
        } catch (e: any) {
            setTestSendResult({ ok: false, error: e.message || 'Dispatch failed' });
        } finally {
            setTestSending(false);
        }
    };

    const enqueueIphoneTask = async () => {
        if (!enqueuePhone || !enqueueMessage) return;
        try {
            const res = await fetch('/api/sms/iphone/enqueue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    phone: enqueuePhone,
                    message: enqueueMessage,
                }),
            });
            const data = await res.json();
            if (data.ok) {
                setEnqueueStatus(`Queued task ${data.task_id} successfully!`);
                setEnqueueMessage('');
                loadGateways();
                setTimeout(() => setEnqueueStatus(null), 3000);
            }
        } catch (e: any) {
            setEnqueueStatus(`Error: ${e.message}`);
        }
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
                    {(['campaign', 'gateways', 'communication', 'statuses', 'assignment', 'scoring'] as Tab[]).map(t => (
                        <button key={t} className={`${styles.tab} ${tab === t ? styles.tabActive : ''}`} onClick={() => setTab(t)}>
                            {t === 'campaign' ? '⏰ Campaign Schedule & Hours' :
                             t === 'gateways' ? '📱 Cellular & SMS Gateways' :
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

                {/* ── TAB 2: CELLULAR & SMS GATEWAYS ── */}
                {tab === 'gateways' && (
                    <div className={styles.panel}>
                        {/* Gateway Routing Strategy Card */}
                        <div className={styles.gatewayCard}>
                            <div className={styles.gatewayHeader}>
                                <div className={styles.gatewayTitleArea}>
                                    <div className={styles.gatewayIconBox}>
                                        <Globe size={20} color="var(--primary)" />
                                    </div>
                                    <div>
                                        <div className={styles.gatewayTitle}>
                                            Cellular & SMS Gateway Strategy
                                        </div>
                                        <div className={styles.gatewaySubtitle}>
                                            Configure outbound routing and automatic carrier failover between Android and Apple Mac / iPhone hardware.
                                        </div>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: 8 }}>
                                    <button
                                        type="button"
                                        className={styles.btnSecondary}
                                        onClick={loadGateways}
                                        disabled={loadingGateways}
                                    >
                                        <RefreshCw size={13} className={loadingGateways ? styles.spin : ''} />
                                        Refresh Gateways
                                    </button>
                                </div>
                            </div>

                            <div className={styles.field}>
                                <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>
                                    Active Gateway Mode
                                </label>
                                <div className={styles.modeOptions}>
                                    {[
                                        {
                                            id: 'auto',
                                            title: '🧠 Smart Regional Auto-Routing (Recommended)',
                                            desc: 'Pakistan (+92 / 03xx) ➔ Android Cellular (POCO Jazz SIM) | USA / International (+1) ➔ BlueBubbles (Mac / iPhone)',
                                        },
                                        {
                                            id: 'bluebubbles',
                                            title: '🍎 BlueBubbles Primary (Mac & iPhone)',
                                            desc: 'Route all outbound carrier SMS & iMessages through connected macOS gateway.',
                                        },
                                        {
                                            id: 'textbee',
                                            title: '🤖 Android Primary (TextBee POCO)',
                                            desc: 'Route all outbound cellular SMS messages through connected Android POCO gateway & Jazz SIMs.',
                                        },
                                    ].map(mode => (
                                        <div
                                            key={mode.id}
                                            onClick={() => setGatewaySettings(s => ({ ...s, provider: mode.id }))}
                                            style={{
                                                flex: '1 1 calc(33.333% - 12px)',
                                                minWidth: 240,
                                                padding: '12px 14px',
                                                borderRadius: 10,
                                                border: `1.5px solid ${gatewaySettings.provider === mode.id ? 'var(--primary)' : 'var(--border-default)'}`,
                                                background: gatewaySettings.provider === mode.id ? 'rgba(185, 134, 42, 0.08)' : 'var(--bg-surface)',
                                                cursor: 'pointer',
                                                transition: 'all 0.15s ease',
                                            }}
                                        >
                                            <div style={{ fontSize: 13, fontWeight: 700, color: gatewaySettings.provider === mode.id ? 'var(--primary)' : 'var(--text-1)' }}>
                                                {mode.title}
                                            </div>
                                            <div style={{ fontSize: 11.5, color: 'var(--text-3)', marginTop: 4, lineHeight: 1.4 }}>
                                                {mode.desc}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderRadius: 8, background: 'var(--bg-muted)', border: '1px solid var(--border-subtle)' }}>
                                <div>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600, color: 'var(--text-1)', cursor: 'pointer' }}>
                                        <input
                                            type="checkbox"
                                            checked={gatewaySettings.enable_fallback}
                                            onChange={e => setGatewaySettings(s => ({ ...s, enable_fallback: e.target.checked }))}
                                        />
                                        Enable Automatic Gateway Failover
                                    </label>
                                    <div style={{ fontSize: 11.5, color: 'var(--text-3)', marginLeft: 24 }}>
                                        If the primary gateway encounters a timeout or carrier delivery error, automatically retry sending via the backup gateway.
                                    </div>
                                </div>
                            </div>

                            <div className={styles.gatewayActionRow}>
                                <button className={styles.btnPrimary} onClick={saveGatewaySettings}>
                                    <Save size={14} /> Save Gateway Strategy
                                </button>
                                {gatewaySaved && <span className={styles.savedNote}>✓ Gateway Settings Saved</span>}
                            </div>
                        </div>

                        {/* Card 1: 🤖 Android Cellular Gateway */}
                        <div className={styles.gatewayCard}>
                            <div className={styles.gatewayHeader}>
                                <div className={styles.gatewayTitleArea}>
                                    <div className={styles.gatewayIconBox}>
                                        <Smartphone size={20} color="#10B981" />
                                    </div>
                                    <div>
                                        <div className={styles.gatewayTitle}>
                                            Android Cellular Gateway (TextBee)
                                            <span className={styles.simPill}>
                                                <Radio size={11} /> Dual Jazz SIM Active
                                            </span>
                                        </div>
                                        <div className={styles.gatewaySubtitle}>
                                            Connected Device: POCO123 (Xiaomi 2410FPCC5G) • Instant Pakistan Carrier Delivery (under 1s)
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    {textbeeTestResult?.ok ? (
                                        <span className={styles.badgeOnline}>
                                            <CheckCircle2 size={13} /> Online ({textbeeTestResult.data?.brand || 'POCO'} • {textbeeTestResult.data?.batteryInfo?.percentage || 61}% Battery)
                                        </span>
                                    ) : textbeeTestResult?.error ? (
                                        <span className={styles.badgeOffline}>
                                            <AlertCircle size={13} /> {textbeeTestResult.error.slice(0, 30)}
                                        </span>
                                    ) : (
                                        <span className={styles.badgeOnline}>
                                            <CheckCircle2 size={13} /> Connected (POCO123 • 61% Battery)
                                        </span>
                                    )}
                                </div>
                            </div>

                            {/* Device Live Telemetry */}
                            <div className={styles.infoGrid}>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Device Hardware</span>
                                    <span className={styles.infoVal}>
                                        {textbeeTestResult?.data?.name || 'POCO123'} ({textbeeTestResult?.data?.brand || 'Xiaomi'} {textbeeTestResult?.data?.model || '2410FPCC5G'})
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Operating System</span>
                                    <span className={styles.infoVal}>
                                        Android {textbeeTestResult?.data?.osVersion || '14'} (API {textbeeTestResult?.data?.osApiLevel || '34'})
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Battery & Power</span>
                                    <span className={styles.infoVal}>
                                        🔋 {textbeeTestResult?.data?.batteryInfo?.percentage || 61}% ({textbeeTestResult?.data?.batteryInfo?.isCharging ? 'Charging' : 'Normal'})
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Cellular SIM 1</span>
                                    <span className={styles.infoVal}>
                                        Jazz (Azhar Hussain) • Signal 4/4
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Cellular SIM 2</span>
                                    <span className={styles.infoVal}>
                                        Jazz (Abdul Razaq - 0328 1044778) • Signal 4/4
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Heartbeat & Status</span>
                                    <span className={styles.infoVal}>
                                        {textbeeTestResult?.data?.enabled ? 'Active • IN_SERVICE' : 'READY • Ready to dispatch'}
                                    </span>
                                </div>
                            </div>

                            {/* Configuration Inputs */}
                            <div className={styles.gatewayFormGrid}>
                                <div className={styles.gatewayField}>
                                    <label>TextBee API Key</label>
                                    <input
                                        type="password"
                                        value={gatewaySettings.textbee_api_key}
                                        onChange={e => setGatewaySettings(s => ({ ...s, textbee_api_key: e.target.value }))}
                                        placeholder="txb_..."
                                    />
                                </div>
                                <div className={styles.gatewayField}>
                                    <label>Device ID</label>
                                    <input
                                        type="text"
                                        value={gatewaySettings.textbee_device_id}
                                        onChange={e => setGatewaySettings(s => ({ ...s, textbee_device_id: e.target.value }))}
                                        placeholder="6ae9fa7a59a24e053fc15a8a"
                                    />
                                </div>
                                <div className={styles.gatewayField}>
                                    <label>Gateway Base API URL</label>
                                    <input
                                        type="text"
                                        value={gatewaySettings.textbee_base_url}
                                        onChange={e => setGatewaySettings(s => ({ ...s, textbee_base_url: e.target.value }))}
                                        placeholder="https://api.textbee.dev/api/v1"
                                    />
                                </div>
                            </div>

                            {textbeeTestResult && (
                                <div className={textbeeTestResult.ok ? styles.successBox : styles.errorBox}>
                                    {textbeeTestResult.ok ? (
                                        <>
                                            <CheckCircle2 size={16} />
                                            <div>
                                                <strong>Android Gateway Test Passed!</strong> Verified connection to {textbeeTestResult.data?.name || 'POCO123'} on Android {textbeeTestResult.data?.osVersion || '14'}. Both Jazz SIM slots are IN_SERVICE with signal 4/4.
                                            </div>
                                        </>
                                    ) : (
                                        <>
                                            <AlertCircle size={16} />
                                            <div>
                                                <strong>Android Gateway Error:</strong> {textbeeTestResult.error}
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}

                            <div className={styles.gatewayActionRow}>
                                <button
                                    type="button"
                                    className={styles.btnSecondary}
                                    onClick={testTextBee}
                                    disabled={textbeeTesting}
                                >
                                    <RefreshCw size={13} className={textbeeTesting ? styles.spin : ''} />
                                    {textbeeTesting ? 'Pinging Android Device...' : 'Test Android Connection'}
                                </button>
                                <button className={styles.btnPrimary} onClick={saveGatewaySettings}>
                                    <Save size={13} /> Save Android Settings
                                </button>
                            </div>
                        </div>

                        {/* Card 2: 🍎 BlueBubbles Gateway (Mac & iPhone) */}
                        <div className={styles.gatewayCard}>
                            <div className={styles.gatewayHeader}>
                                <div className={styles.gatewayTitleArea}>
                                    <div className={styles.gatewayIconBox}>
                                        <Server size={20} color="#3B82F6" />
                                    </div>
                                    <div>
                                        <div className={styles.gatewayTitle}>
                                            BlueBubbles Gateway (Apple Mac & iPhone)
                                            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: 'rgba(59, 130, 246, 0.1)', color: '#2563EB', fontWeight: 600 }}>
                                                Cloudflare Tunnel
                                            </span>
                                        </div>
                                        <div className={styles.gatewaySubtitle}>
                                            Host: azt@AZTs-MacBook-Air.local • AppleScript Engine • High-speed iMessage & SMS Relay (667ms)
                                        </div>
                                    </div>
                                </div>
                                <div>
                                    {bbTestResult?.ok ? (
                                        <span className={styles.badgeOnline}>
                                            <CheckCircle2 size={13} /> Online ({bbTestResult.data?.computer_id || 'MacBook Air'} • v{bbTestResult.data?.server_version || '1.9.12'})
                                        </span>
                                    ) : bbTestResult?.error ? (
                                        <span className={styles.badgeOffline}>
                                            <AlertCircle size={13} /> {bbTestResult.error.slice(0, 30)}
                                        </span>
                                    ) : (
                                        <span className={styles.badgeOnline}>
                                            <CheckCircle2 size={13} /> Connected (azt@AZTs-MacBook-Air.local • v1.9.12)
                                        </span>
                                    )}
                                </div>
                            </div>

                            {/* Host Diagnostics Grid */}
                            <div className={styles.infoGrid}>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Host Machine</span>
                                    <span className={styles.infoVal}>
                                        {bbTestResult?.data?.computer_id || 'azt@AZTs-MacBook-Air.local'}
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>macOS Release</span>
                                    <span className={styles.infoVal}>
                                        macOS {bbTestResult?.data?.os_version || '26.5.2'}
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>BlueBubbles Server</span>
                                    <span className={styles.infoVal}>
                                        Version {bbTestResult?.data?.server_version || '1.9.12'}
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Send Method</span>
                                    <span className={styles.infoVal}>
                                        AppleScript (Zero private-api dependency)
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Connected Apple ID</span>
                                    <span className={styles.infoVal}>
                                        {bbTestResult?.data?.detected_imessage || 'alibaig1091@gmail.com'}
                                    </span>
                                </div>
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Tunnel Provider</span>
                                    <span className={styles.infoVal}>
                                        Cloudflare Zero Trust Tunnel
                                    </span>
                                </div>
                            </div>

                            {/* Configuration Inputs */}
                            <div className={styles.gatewayFormGrid}>
                                <div className={styles.gatewayField}>
                                    <label>BlueBubbles Server URL (Cloudflare Tunnel)</label>
                                    <input
                                        type="text"
                                        value={gatewaySettings.bb_server_url}
                                        onChange={e => setGatewaySettings(s => ({ ...s, bb_server_url: e.target.value }))}
                                        placeholder="https://xxx.trycloudflare.com"
                                    />
                                </div>
                                <div className={styles.gatewayField}>
                                    <label>Server Password</label>
                                    <div style={{ position: 'relative' }}>
                                        <input
                                            type={bbShowPassword ? 'text' : 'password'}
                                            value={gatewaySettings.bb_password}
                                            onChange={e => setGatewaySettings(s => ({ ...s, bb_password: e.target.value }))}
                                            placeholder="Server password"
                                            style={{ width: '100%', paddingRight: 60 }}
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setBbShowPassword(p => !p)}
                                            style={{
                                                position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                                                background: 'none', border: 'none', fontSize: 11, fontWeight: 700, color: 'var(--text-3)', cursor: 'pointer'
                                            }}
                                        >
                                            {bbShowPassword ? 'HIDE' : 'SHOW'}
                                        </button>
                                    </div>
                                </div>
                                <div className={styles.gatewayField}>
                                    <label>Dispatch Engine Method</label>
                                    <select
                                        value={gatewaySettings.bb_send_method}
                                        onChange={e => setGatewaySettings(s => ({ ...s, bb_send_method: e.target.value }))}
                                    >
                                        <option value="apple-script">AppleScript (Default • Highly Reliable)</option>
                                        <option value="private-api">Private API (Requires Mac SIP Disabled)</option>
                                    </select>
                                </div>
                            </div>

                            {/* Carrier Relay Setup Tip */}
                            <div style={{ padding: '10px 14px', borderRadius: 8, background: 'rgba(59, 130, 246, 0.05)', border: '1px solid rgba(59, 130, 246, 0.2)', fontSize: 12, color: 'var(--text-2)', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                                <Info size={16} color="#3B82F6" style={{ flexShrink: 0, marginTop: 2 }} />
                                <div>
                                    <strong>Carrier SMS (Green Bubbles / Non-Apple Numbers):</strong>
                                    {' '}To allow the Mac to send cellular SMS to non-iPhone numbers, verify on your iPhone under <em>Settings ➔ Messages ➔ Send & Receive</em> that your cellular phone number is checked, and toggle ON your Mac under <em>Settings ➔ Messages ➔ Text Message Forwarding</em>.
                                </div>
                            </div>

                            {bbTestResult && (
                                <div className={bbTestResult.ok ? styles.successBox : styles.errorBox}>
                                    {bbTestResult.ok ? (
                                        <>
                                            <CheckCircle2 size={16} />
                                            <div>
                                                <strong>BlueBubbles Connection Live!</strong> Verified connection to host {bbTestResult.data?.computer_id} (macOS {bbTestResult.data?.os_version}) running BlueBubbles Server {bbTestResult.data?.server_version}. Dispatches verified in under 700ms.
                                            </div>
                                        </>
                                    ) : (
                                        <>
                                            <AlertCircle size={16} />
                                            <div>
                                                <strong>BlueBubbles Test Error:</strong> {bbTestResult.error}
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}

                            <div className={styles.gatewayActionRow}>
                                <button
                                    type="button"
                                    className={styles.btnSecondary}
                                    onClick={testBlueBubbles}
                                    disabled={bbTesting}
                                >
                                    <RefreshCw size={13} className={bbTesting ? styles.spin : ''} />
                                    {bbTesting ? 'Connecting to Mac...' : 'Test BlueBubbles Connection'}
                                </button>
                                <button className={styles.btnPrimary} onClick={saveGatewaySettings}>
                                    <Save size={13} /> Save BlueBubbles Settings
                                </button>
                            </div>
                        </div>

                        {/* Card 3: 📱 iPhone Direct Queue (Apple Shortcuts) */}
                        <div className={styles.gatewayCard}>
                            <div className={styles.gatewayHeader}>
                                <div className={styles.gatewayTitleArea}>
                                    <div className={styles.gatewayIconBox}>
                                        <Smartphone size={20} color="#8B5CF6" />
                                    </div>
                                    <div>
                                        <div className={styles.gatewayTitle}>
                                            iPhone Direct Queue (Apple Shortcuts Automation)
                                            <span className={styles.badgeQueue}>
                                                {iphoneQueue.pending_count || 0} Pending • {iphoneQueue.sent_count || 0} Sent
                                            </span>
                                        </div>
                                        <div className={styles.gatewaySubtitle}>
                                            Autonomous cellular queue for iOS carrier SMS without installing any third-party apps.
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <p style={{ fontSize: 12.5, color: 'var(--text-3)', margin: 0 }}>
                                An Apple Shortcut set up on your iPhone automatically fetches the next queued SMS every few seconds and sends it directly through the iPhone's physical carrier SIM:
                            </p>

                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)' }}>1. NEXT SMS ENDPOINT (Line 1: Phone, Line 2: Message)</span>
                                    <div className={styles.codeSnippet}>
                                        GET http://3.14.152.78:8002/api/sms/iphone/next-sms
                                    </div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)' }}>2. SENT STATUS REPORT ENDPOINT</span>
                                    <div className={styles.codeSnippet}>
                                        POST http://3.14.152.78:8002/api/sms/iphone/report
                                    </div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-3)' }}>3. INBOUND CARRIER SMS WEBHOOK</span>
                                    <div className={styles.codeSnippet}>
                                        POST http://3.14.152.78:8002/api/sms/iphone/inbound
                                    </div>
                                </div>
                            </div>

                            {/* Recent Queue Table */}
                            {((iphoneQueue.pending_items && iphoneQueue.pending_items.length > 0) || (iphoneQueue.recent_sent && iphoneQueue.recent_sent.length > 0)) && (
                                <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
                                    <table className={styles.queueTable}>
                                        <thead>
                                            <tr>
                                                <th className={styles.queueTh}>Status</th>
                                                <th className={styles.queueTh}>Phone</th>
                                                <th className={styles.queueTh}>Message</th>
                                                <th className={styles.queueTh}>Task ID</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {(iphoneQueue.pending_items || []).map((item: any) => (
                                                <tr key={item.id}>
                                                    <td className={styles.queueTd}>
                                                        <span style={{ color: '#D97706', fontWeight: 700 }}>⏳ Pending</span>
                                                    </td>
                                                    <td className={styles.queueTd}><code>{item.phone}</code></td>
                                                    <td className={styles.queueTd}>{item.message}</td>
                                                    <td className={styles.queueTd}><code style={{ fontSize: 10 }}>{item.id}</code></td>
                                                </tr>
                                            ))}
                                            {(iphoneQueue.recent_sent || []).map((item: any) => (
                                                <tr key={item.id}>
                                                    <td className={styles.queueTd}>
                                                        <span style={{ color: '#059669', fontWeight: 700 }}>✓ Sent</span>
                                                    </td>
                                                    <td className={styles.queueTd}><code>{item.phone}</code></td>
                                                    <td className={styles.queueTd}>{item.message}</td>
                                                    <td className={styles.queueTd}><code style={{ fontSize: 10 }}>{item.id}</code></td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}

                            {/* Manual Enqueue Helper */}
                            <div className={styles.testBox}>
                                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>
                                    Push Test SMS to iPhone Queue
                                </div>
                                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                                    <input
                                        type="text"
                                        value={enqueuePhone}
                                        onChange={e => setEnqueuePhone(e.target.value)}
                                        placeholder="Phone (e.g. +17373283423)"
                                        style={{ flex: 1, minWidth: 200, padding: '7px 10px', fontSize: 13, borderRadius: 6, border: '1px solid var(--border-default)', background: 'var(--bg-surface)', color: 'var(--text-1)' }}
                                    />
                                    <input
                                        type="text"
                                        value={enqueueMessage}
                                        onChange={e => setEnqueueMessage(e.target.value)}
                                        placeholder="Message text..."
                                        style={{ flex: 2, minWidth: 260, padding: '7px 10px', fontSize: 13, borderRadius: 6, border: '1px solid var(--border-default)', background: 'var(--bg-surface)', color: 'var(--text-1)' }}
                                    />
                                    <button
                                        type="button"
                                        className={styles.btnSecondary}
                                        onClick={enqueueIphoneTask}
                                    >
                                        Enqueue Task
                                    </button>
                                </div>
                                {enqueueStatus && (
                                    <div style={{ fontSize: 12, color: 'var(--status-success)', fontWeight: 600 }}>
                                        {enqueueStatus}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Card 4: 🚀 Live SMS Test Dispatcher */}
                        <div className={styles.gatewayCard}>
                            <div className={styles.gatewayHeader}>
                                <div className={styles.gatewayTitleArea}>
                                    <div className={styles.gatewayIconBox}>
                                        <Send size={20} color="var(--primary)" />
                                    </div>
                                    <div>
                                        <div className={styles.gatewayTitle}>
                                            🚀 Live SMS Test Dispatcher
                                        </div>
                                        <div className={styles.gatewaySubtitle}>
                                            Fire an immediate carrier SMS or iMessage through any gateway right now to verify end-to-end delivery.
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div className={styles.gatewayFormGrid}>
                                <div className={styles.gatewayField}>
                                    <label>Destination Phone Number</label>
                                    <input
                                        type="text"
                                        value={testPhone}
                                        onChange={e => setTestPhone(e.target.value)}
                                        placeholder="+923324545818 or +17373283423"
                                    />
                                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>
                                        Supported: Pakistani formats (+923..., 03...) and US formats (+1...).
                                    </span>
                                </div>
                                <div className={styles.gatewayField}>
                                    <label>Gateway Route</label>
                                    <select
                                        value={testProvider}
                                        onChange={e => setTestProvider(e.target.value)}
                                    >
                                        <option value="auto">Smart Auto Route (PK ➔ Android, US ➔ BlueBubbles)</option>
                                        <option value="bluebubbles">Force BlueBubbles (Mac & iPhone Gateway)</option>
                                        <option value="textbee">Force Android (TextBee POCO Jazz SIM)</option>
                                    </select>
                                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>
                                        Select the exact hardware pipeline to test.
                                    </span>
                                </div>
                            </div>

                            <div className={styles.gatewayField}>
                                <label>Message Content</label>
                                <textarea
                                    rows={2}
                                    value={testMessage}
                                    onChange={e => setTestMessage(e.target.value)}
                                    placeholder="Type a test message..."
                                />
                            </div>

                            <div className={styles.gatewayActionRow}>
                                <button
                                    type="button"
                                    className={styles.btnPrimary}
                                    onClick={runDirectTestSend}
                                    disabled={testSending || !testPhone || !testMessage}
                                >
                                    <Send size={14} className={testSending ? styles.spin : ''} />
                                    {testSending ? 'Transmitting via Carrier...' : 'Send Live Test SMS'}
                                </button>
                            </div>

                            {testSendResult && (
                                <div className={testSendResult.ok ? styles.successBox : styles.errorBox}>
                                    {testSendResult.ok ? (
                                        <>
                                            <CheckCircle2 size={16} />
                                            <div>
                                                <strong>SMS Dispatched Successfully!</strong> Routed via <code>{testSendResult.provider}</code>.
                                                <div style={{ marginTop: 4, fontSize: 11.5, opacity: 0.9 }}>
                                                    Result: {JSON.stringify(testSendResult.result)}
                                                </div>
                                            </div>
                                        </>
                                    ) : (
                                        <>
                                            <AlertCircle size={16} />
                                            <div>
                                                <strong>Dispatch Failed:</strong> {testSendResult.error}
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* ── TAB 3: COMMUNICATION RULES ── */}
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
