'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import styles from './automation.module.css';

interface Settings {
    sms_auto_enabled: boolean;
    sms_followup_wait_hours: number;
    call_on_confirm_enabled: boolean;
    call_on_confirm_wait_minutes: number;
    call_on_silence_enabled: boolean;
}

const DEFAULTS: Settings = {
    sms_auto_enabled: true,
    sms_followup_wait_hours: 23,
    call_on_confirm_enabled: true,
    call_on_confirm_wait_minutes: 45,
    call_on_silence_enabled: true,
};

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
    return (
        <button
            type="button"
            className={styles.toggleSwitch}
            onClick={onClick}
            style={{ background: on ? 'var(--primary)' : '#4b5563' }}
            aria-pressed={on}
        >
            <div className={styles.toggleThumb} style={{ left: on ? 21 : 3 }} />
        </button>
    );
}

function Step({ n, on, label, detail }: { n: number; on: boolean; label: string; detail: string }) {
    return (
        <div className={`${styles.timelineStep} ${on ? '' : styles.timelineStepOff}`}>
            <div className={styles.timelineDot}>{n}</div>
            <div className={styles.timelineBody}>
                <div className={styles.timelineLabel}>{label}</div>
                {on
                    ? <div className={styles.timelineDetail}>{detail}</div>
                    : <div className={styles.timelineOffNote}>Turned off below — this step is skipped</div>}
            </div>
        </div>
    );
}

function Timeline({ settings }: { settings: Settings }) {
    return (
        <div className={styles.timelineCard}>
            <div className={styles.timelineTitle}>How this works, step by step</div>
            <div className={styles.timelineSub}>This is the exact path every new lead follows, based on your settings below.</div>

            <Step n={1} on
                label="New lead comes in → text sent right away"
                detail={`A friendly intro text goes out immediately asking what coverage they need.`} />

            <Step n={2} on={settings.sms_auto_enabled}
                label={`No reply after ${settings.sms_followup_wait_hours}h → second text sent`}
                detail={`A different follow-up text — not a repeat — if they haven't replied yet.`} />

            <Step n={3} on
                label="They reply, any time → conversation starts"
                detail={`The AI answers questions, and once they show real interest, asks if they'd like a call.`} />

            <Step n={4} on={settings.call_on_confirm_enabled}
                label={`They say yes to a call → we call ${settings.call_on_confirm_wait_minutes} min later`}
                detail={`The call is briefed on the full text conversation — it won't repeat questions already answered.`} />

            <Step n={5} on={settings.call_on_silence_enabled}
                label="Still no reply after 2 texts → one check-in call"
                detail={`"We've texted you twice about coverage — still interested?" No pressure either way.`} />

            <div className={styles.timelineStep} style={{ paddingBottom: 4 }}>
                <div className={styles.timelineDot}>6</div>
                <div className={styles.timelineBody}>
                    <div className={styles.timelineLabel}>Appointment booked → done</div>
                    <div className={styles.timelineDetail}>By text or on a call — either way, the lead moves to Appointment Scheduled.</div>
                </div>
            </div>
        </div>
    );
}

export function QuickSetup() {
    const { accessToken } = useAuth();
    const [settings, setSettings] = useState<Settings>(DEFAULTS);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [dirty, setDirty] = useState(false);

    const h = accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined;

    const load = useCallback(async () => {
        if (!accessToken) return;
        setLoading(true);
        try {
            const res = await fetch('/api/automation-settings', { headers: h });
            const d = await res.json();
            if (d.success) setSettings({ ...DEFAULTS, ...d.data.settings });
        } catch {}
        setLoading(false);
    }, [accessToken]);

    useEffect(() => { load(); }, [load]);

    const update = (patch: Partial<Settings>) => {
        setSettings(prev => ({ ...prev, ...patch }));
        setDirty(true);
        setSaved(false);
    };

    const save = async () => {
        if (!accessToken) return;
        setSaving(true);
        try {
            const res = await fetch('/api/automation-settings', {
                method: 'PATCH',
                headers: { ...h, 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            });
            const d = await res.json();
            if (d.success) {
                setSettings({ ...DEFAULTS, ...d.data.settings });
                setDirty(false);
                setSaved(true);
            }
        } catch {}
        setSaving(false);
    };

    if (loading) {
        return <div style={{ color: 'var(--text-3)', fontSize: 13 }}>Loading…</div>;
    }

    return (
        <div className={styles.quickWrap}>
            <Timeline settings={settings} />

            <div className={styles.settingsCard}>
                <div className={styles.settingsCardTitle}>SMS Automation</div>

                <div className={styles.toggleRow}>
                    <div className={styles.toggleInfo}>
                        <div className={styles.toggleLabel}>Text new leads automatically</div>
                        <div className={styles.toggleDesc}>
                            Every new lead gets an intro text right away, and a follow-up text if they don&apos;t reply.
                        </div>
                    </div>
                    <Toggle on={settings.sms_auto_enabled} onClick={() => update({ sms_auto_enabled: !settings.sms_auto_enabled })} />
                </div>

                {settings.sms_auto_enabled && (
                    <div className={styles.subRow}>
                        Wait before sending the follow-up text:
                        <input
                            type="number" min={1} max={72}
                            className={styles.numberInput}
                            value={settings.sms_followup_wait_hours}
                            onChange={e => update({ sms_followup_wait_hours: Math.max(1, parseInt(e.target.value) || 1) })}
                        />
                        hours
                    </div>
                )}
            </div>

            <div className={styles.settingsCard}>
                <div className={styles.settingsCardTitle}>Call Automation</div>

                <div className={styles.toggleRow}>
                    <div className={styles.toggleInfo}>
                        <div className={styles.toggleLabel}>Call once a lead confirms interest</div>
                        <div className={styles.toggleDesc}>
                            If a lead says yes to a call over text (or asks for one themselves), we call them —
                            briefed on the full text conversation so nothing gets repeated.
                        </div>
                    </div>
                    <Toggle on={settings.call_on_confirm_enabled} onClick={() => update({ call_on_confirm_enabled: !settings.call_on_confirm_enabled })} />
                </div>

                {settings.call_on_confirm_enabled && (
                    <div className={styles.subRow}>
                        Wait before calling:
                        <input
                            type="number" min={5} max={180}
                            className={styles.numberInput}
                            value={settings.call_on_confirm_wait_minutes}
                            onChange={e => update({ call_on_confirm_wait_minutes: Math.max(5, parseInt(e.target.value) || 5) })}
                        />
                        minutes
                    </div>
                )}

                <div className={styles.toggleRow}>
                    <div className={styles.toggleInfo}>
                        <div className={styles.toggleLabel}>Call if a lead goes silent after 2 texts</div>
                        <div className={styles.toggleDesc}>
                            If they never reply to either text, we place one check-in call — &quot;we&apos;ve texted
                            you twice, still interested?&quot; — instead of texting a third time.
                        </div>
                    </div>
                    <Toggle on={settings.call_on_silence_enabled} onClick={() => update({ call_on_silence_enabled: !settings.call_on_silence_enabled })} />
                </div>
            </div>

            <div className={styles.saveBar}>
                <button className={styles.btnPrimary} onClick={save} disabled={!dirty || saving}>
                    {saving ? 'Saving…' : 'Save Changes'}
                </button>
                {saved && !dirty && (
                    <span className={styles.savedNote}><Check size={13} style={{ verticalAlign: -2 }} /> Saved</span>
                )}
            </div>
        </div>
    );
}
