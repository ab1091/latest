'use client';

import { useState, useEffect } from 'react';
import { AlertTriangle, Clock, User, MessageCircle, X, BedDouble, Stethoscope, Building2, Zap, ArrowLeft } from 'lucide-react';
import styles from './EmergencyModal.module.css';

interface Provider { id: string; name: string; specialty: string; }

interface EmergencyModalProps {
    isOpen: boolean;
    onClose: () => void;
    accessToken: string;
    onSuccess: (blockId: string, affectedCount: number) => void;
}

const BLOCK_TYPES = [
    {
        key: 'leave',
        label: 'Doctor on Leave',
        icon: '🏖️',
        reason: 'Doctor on leave',
        aiPrompt: 'Your doctor is on leave today and unfortunately cannot see you. We sincerely apologize for the inconvenience. We will reschedule your appointment at the earliest available slot.',
    },
    {
        key: 'emergency',
        label: 'Emergency',
        icon: '🚨',
        reason: 'Doctor unavailable due to emergency',
        aiPrompt: 'Your doctor has an urgent emergency and is unable to attend today. We are sorry for the short notice and will reschedule your appointment as soon as possible.',
    },
    {
        key: 'clinic',
        label: 'Clinic Closed',
        icon: '🏥',
        reason: 'Clinic closed',
        aiPrompt: 'Our clinic is closed today and your appointment cannot be accommodated. We apologize for the inconvenience and will contact you to reschedule.',
    },
    {
        key: 'custom',
        label: 'Custom',
        icon: '✏️',
        reason: '',
        aiPrompt: '',
    },
];

const pad = (n: number) => String(n).padStart(2, '0');
const toLocal = (d: Date) =>
    `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

const DATE_PRESETS = [
    { key: 'today',     label: 'Today' },
    { key: 'tomorrow',  label: 'Tomorrow' },
    { key: 'morning',   label: 'This Morning' },
    { key: 'afternoon', label: 'This Afternoon' },
    { key: 'week',      label: 'This Week' },
];

function calcPreset(key: string): { start: string; end: string } {
    const now = new Date();
    const d = (h: number, m = 0) => new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m);
    switch (key) {
        case 'today':     return { start: toLocal(d(0,0)), end: toLocal(d(23,59)) };
        case 'tomorrow':  { const s = d(0,0); s.setDate(s.getDate()+1); const e = d(23,59); e.setDate(e.getDate()+1); return { start: toLocal(s), end: toLocal(e) }; }
        case 'morning':   return { start: toLocal(d(8,0)), end: toLocal(d(12,0)) };
        case 'afternoon': return { start: toLocal(d(13,0)), end: toLocal(d(18,0)) };
        case 'week':      { const e = d(23,59); e.setDate(e.getDate()+6); return { start: toLocal(d(0,0)), end: toLocal(e) }; }
        default:          return { start: '', end: '' };
    }
}

export function EmergencyModal({ isOpen, onClose, accessToken, onSuccess }: EmergencyModalProps) {
    const [providers, setProviders]             = useState<Provider[]>([]);
    const [selectedProviderId, setSelectedProviderId] = useState('');
    const [blockType, setBlockType]             = useState('leave');
    const [startTime, setStartTime]             = useState('');
    const [endTime, setEndTime]                 = useState('');
    const [reason, setReason]                   = useState('');
    const [aiExplanation, setAiExplanation]     = useState('');
    const [activePreset, setActivePreset]       = useState<string | null>(null);
    const [isLoading, setIsLoading]             = useState(false);
    const [error, setError]                     = useState<string | null>(null);
    const [impactCount, setImpactCount]         = useState<number | null>(null);

    const reset = () => {
        setSelectedProviderId(''); setBlockType('leave'); setStartTime(''); setEndTime('');
        setReason(''); setAiExplanation(''); setActivePreset(null); setImpactCount(null); setError(null);
    };

    useEffect(() => {
        if (isOpen && accessToken) {
            fetch('/api/appointments/providers', { headers: { Authorization: `Bearer ${accessToken}` } })
                .then(r => r.json()).then(d => setProviders(d.data?.providers || [])).catch(() => {});
        } else if (!isOpen) reset();
    }, [isOpen, accessToken]);

    // When block type changes, auto-fill reason + AI prompt (unless custom)
    useEffect(() => {
        const t = BLOCK_TYPES.find(t => t.key === blockType);
        if (t && blockType !== 'custom') {
            setReason(t.reason);
            setAiExplanation(t.aiPrompt);
        } else {
            setReason(''); setAiExplanation('');
        }
    }, [blockType]);

    // Impact check
    useEffect(() => {
        if (!selectedProviderId || !startTime || !endTime) { setImpactCount(null); return; }
        const start = new Date(startTime), end = new Date(endTime);
        if (end <= start) { setImpactCount(null); return; }
        const timer = setTimeout(() => {
            const params = new URLSearchParams({ providerId: selectedProviderId, startTime: start.toISOString(), endTime: end.toISOString() });
            fetch(`/api/emergency-blocks/impact?${params}`, { headers: { Authorization: `Bearer ${accessToken}` } })
                .then(r => r.json()).then(d => setImpactCount(d.data?.count ?? null)).catch(() => {});
        }, 500);
        return () => clearTimeout(timer);
    }, [selectedProviderId, startTime, endTime, accessToken]);

    const applyDatePreset = (key: string) => {
        const { start, end } = calcPreset(key);
        setStartTime(start); setEndTime(end); setActivePreset(key);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedProviderId || !startTime || !endTime || !reason) {
            setError('Please fill in Provider, dates, and reason.'); return;
        }
        if (new Date(endTime) <= new Date(startTime)) {
            setError('End time must be after start time.'); return;
        }
        setIsLoading(true); setError(null);
        try {
            const res = await fetch('/api/emergency-blocks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
                body: JSON.stringify({
                    providerId: selectedProviderId,
                    startTime: new Date(startTime).toISOString(),
                    endTime: new Date(endTime).toISOString(),
                    reason,
                    aiExplanation: aiExplanation || reason,
                }),
            });
            const data = await res.json();
            if (res.ok) { onSuccess(data.data.blockId, data.data.affectedCount); onClose(); }
            else setError(data.error || 'Failed to create emergency block');
        } catch { setError('Connection error. Please try again.'); }
        finally { setIsLoading(false); }
    };

    if (!isOpen) return null;
    const endBeforeStart = !!(startTime && endTime && new Date(endTime) <= new Date(startTime));

    return (
        <div className={styles.backdrop}>
            <div className={styles.modal}>
                <div className={styles.header}>
                    <button onClick={onClose} className={styles.backBtn}><ArrowLeft size={18} /></button>
                    <div className={styles.titleIcon}>
                        <AlertTriangle size={22} color="var(--status-danger)" />
                        <h2>Emergency Block</h2>
                    </div>
                    <button onClick={onClose} className={styles.closeBtn}><X size={20} /></button>
                </div>

                <form onSubmit={handleSubmit} className={styles.form}>
                    {error && <div className={styles.error}><AlertTriangle size={15} /> {error}</div>}

                    {/* Block Type */}
                    <div className={styles.field}>
                        <label>Block Type</label>
                        <div className={styles.typeGrid}>
                            {BLOCK_TYPES.map(t => (
                                <button key={t.key} type="button"
                                    className={`${styles.typeBtn} ${blockType === t.key ? styles.typeBtnActive : ''}`}
                                    onClick={() => setBlockType(t.key)} disabled={isLoading}>
                                    <span className={styles.typeIcon}>{t.icon}</span>
                                    <span>{t.label}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Provider */}
                    <div className={styles.field}>
                        <label><User size={13} /> Provider</label>
                        <select value={selectedProviderId} onChange={e => setSelectedProviderId(e.target.value)} disabled={isLoading}>
                            <option value="">Select provider…</option>
                            {providers.map(p => <option key={p.id} value={p.id}>{p.name} ({p.specialty})</option>)}
                        </select>
                    </div>

                    {/* Date presets */}
                    <div className={styles.field}>
                        <label><Clock size={13} /> Date</label>
                        <div className={styles.presets}>
                            {DATE_PRESETS.map(p => (
                                <button key={p.key} type="button"
                                    className={`${styles.presetBtn} ${activePreset === p.key ? styles.active : ''}`}
                                    onClick={() => applyDatePreset(p.key)} disabled={isLoading}>
                                    {p.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className={styles.row}>
                        <div className={styles.field}>
                            <label>From</label>
                            <input type="datetime-local" value={startTime}
                                onChange={e => { setStartTime(e.target.value); setActivePreset(null); }} disabled={isLoading} />
                        </div>
                        <div className={styles.field}>
                            <label>Until</label>
                            <input type="datetime-local" value={endTime}
                                onChange={e => { setEndTime(e.target.value); setActivePreset(null); }} disabled={isLoading}
                                style={endBeforeStart ? { borderColor: 'var(--status-danger)' } : {}} />
                        </div>
                    </div>

                    {impactCount !== null && (
                        <div className={styles.impactInfo}>
                            <AlertTriangle size={15} />
                            <span>
                                <strong>{impactCount}</strong> appointment{impactCount !== 1 ? 's' : ''} affected.
                                {impactCount > 0 && ' AI will call each patient to reschedule.'}
                            </span>
                        </div>
                    )}

                    {/* Reason */}
                    <div className={styles.field}>
                        <label>Reason</label>
                        <input type="text" placeholder="e.g. Doctor on medical leave"
                            value={reason} onChange={e => setReason(e.target.value)} disabled={isLoading} />
                    </div>

                    {/* AI Prompt */}
                    <div className={styles.field}>
                        <label><MessageCircle size={13} /> AI Prompt — what the bot tells patients</label>
                        <textarea rows={3} value={aiExplanation}
                            placeholder="What should the AI say to patients on the call?"
                            onChange={e => setAiExplanation(e.target.value)} disabled={isLoading} />
                        <p className={styles.footerHint}>Auto-filled based on block type. Edit as needed.</p>
                    </div>

                    <div className={styles.actions}>
                        <button type="button" onClick={onClose} disabled={isLoading} className={styles.cancelBtn}>Cancel</button>
                        <button type="submit" disabled={isLoading || endBeforeStart} className={styles.submitBtn}>
                            {isLoading ? 'Activating…' : 'Activate Emergency Block'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
