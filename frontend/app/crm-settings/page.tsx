'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Settings2, Save } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { hasModuleAccess } from '@/lib/permissions';
import styles from './crm-settings.module.css';

type Tab = 'statuses' | 'assignment' | 'scoring' | 'pipeline' | 'communication';

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

export default function CrmSettingsPage() {
    const { accessToken, isLoading, user } = useAuth();
    const router = useRouter();
    const [tab, setTab] = useState<Tab>('statuses');
    const [saved, setSaved] = useState(false);

    const [stages, setStages] = useState<Stage[]>([]);
    const [assignmentMode, setAssignmentMode] = useState('manual');
    const [assignmentUserIds, setAssignmentUserIds] = useState<string[]>([]);
    const [staff, setStaff] = useState<StaffUser[]>([]);
    const [scoringRules, setScoringRules] = useState<ScoringRule[]>([]);
    const [commRules, setCommRules] = useState({
        quiet_hours_start: '09:00', quiet_hours_end: '20:00', timezone: 'America/New_York',
        max_sms_per_day: 5, max_calls_per_day: 3,
        channels_enabled: { sms: true, whatsapp: true, call: true, email: false } as Record<string, boolean>,
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
        if (commRes.success) setCommRules(commRes.data.rule);
        if (staffRes?.success) setStaff(staffRes.data.users || staffRes.data || []);
    }, [accessToken]);

    useEffect(() => { load(); }, [load]);

    const flash = () => { setSaved(true); setTimeout(() => setSaved(false), 2000); };

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

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>
                <div className={styles.header}>
                    <div className={styles.headerIcon}><Settings2 size={22} /></div>
                    <div className={styles.headerInfo}>
                        <h1>CRM Settings</h1>
                        <p>Lead statuses, assignment rules, scoring, pipeline, and communication policy.</p>
                    </div>
                </div>

                <div className={styles.tabRail}>
                    {(['statuses', 'assignment', 'scoring', 'pipeline', 'communication'] as Tab[]).map(t => (
                        <button key={t} className={`${styles.tab} ${tab === t ? styles.tabActive : ''}`} onClick={() => setTab(t)}>
                            {t === 'statuses' ? 'Lead Statuses' : t === 'assignment' ? 'Assignment Rules' :
                                t === 'scoring' ? 'Lead Scoring' : t === 'pipeline' ? 'Pipeline' : 'Communication Rules'}
                        </button>
                    ))}
                </div>

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

                {tab === 'pipeline' && (
                    <div className={styles.panel}>
                        <div className={styles.funnelBar}>
                            {stages.map(s => (
                                <div key={s.key} className={styles.funnelSegment} style={{ background: s.color }}>{s.label}</div>
                            ))}
                        </div>
                        <p style={{ fontSize: 12.5, color: 'var(--text-3)' }}>
                            Stage colors/labels are edited in the Lead Statuses tab. Automation for a stage entry
                            (what happens when a lead reaches it) is configured in the Automation &amp; Lead Behavior Engine.
                        </p>
                        <button className={styles.btnSecondary} onClick={() => router.push('/automation')}>
                            Configure stage automation →
                        </button>
                    </div>
                )}

                {tab === 'assignment' && (
                    <div className={styles.panel}>
                        <div className={styles.field}>
                            <label>Assignment Mode</label>
                            <div className={styles.modeOptions}>
                                {[
                                    { v: 'manual', l: 'Manual' },
                                    { v: 'round_robin', l: 'Round Robin' },
                                    { v: 'team_based', l: 'Team Based (load-balanced)' },
                                    { v: 'territory_based', l: 'Territory Based' },
                                ].map(o => (
                                    <button key={o.v} className={`${styles.modeOption} ${assignmentMode === o.v ? styles.modeOptionActive : ''}`}
                                        onClick={() => setAssignmentMode(o.v)}>{o.l}</button>
                                ))}
                            </div>
                        </div>

                        {(assignmentMode === 'round_robin' || assignmentMode === 'team_based') && (
                            <div className={styles.field}>
                                <label>Eligible staff</label>
                                <div className={styles.staffCheckList}>
                                    {staff.filter(u => u.role === 'staff' || u.role === 'admin').map(u => (
                                        <label key={u.id} className={styles.staffCheckItem}>
                                            <input type="checkbox" checked={assignmentUserIds.includes(u.id)} onChange={() => toggleAssignmentUser(u.id)} />
                                            {[u.firstName, u.lastName].filter(Boolean).join(' ') || u.email}
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
            </div>
        </div>
    );
}
