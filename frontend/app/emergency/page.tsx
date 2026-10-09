'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { AlertTriangle, CheckCircle, Clock, ShieldAlert, XCircle, Phone, PhoneOff, PhoneMissed } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { SideNav } from '@/components/SideNav/SideNav';
import styles from './emergency.module.css';

interface Provider {
    id: string;
    name: string;
    specialty: string;
}

interface EmergencyBlock {
    id: string;
    provider_id: string;
    provider_name?: string | null;
    start_time: string;
    end_time: string;
    reason: string;
    ai_explanation: string | null;
    status: 'active' | 'resolved';
    created_at: string;
}

const BLOCK_TYPES = [
    { key: 'leave', label: 'Doctor on Leave', reason: 'Doctor on leave', aiPrompt: 'Your doctor is on leave today and cannot see you. We apologize and will help reschedule.' },
    { key: 'emergency', label: 'Emergency', reason: 'Doctor unavailable due to emergency', aiPrompt: 'Your doctor has an urgent emergency and is unable to attend today. We are sorry for the short notice and will help reschedule.' },
    { key: 'clinic', label: 'Clinic Closed', reason: 'Clinic closed', aiPrompt: 'Our clinic is closed today and your appointment cannot be accommodated. We apologize and will contact you to reschedule.' },
    { key: 'custom', label: 'Custom', reason: '', aiPrompt: '' },
];

export default function EmergencyPage() {
    const { accessToken } = useAuth();

    const [providers, setProviders] = useState<Provider[]>([]);
    const [blocks, setBlocks] = useState<EmergencyBlock[]>([]);
    const [emergencyCalls, setEmergencyCalls] = useState<Record<string, any[]>>({});
    const [providerSearch, setProviderSearch] = useState('');
    const [selectedProviderId, setSelectedProviderId] = useState('');
    const [dropdownOpen, setDropdownOpen] = useState(false);
    const [blockType, setBlockType] = useState('leave');
    const [startTime, setStartTime] = useState('');
    const [endTime, setEndTime] = useState('');
    const [reason, setReason] = useState('');
    const [aiExplanation, setAiExplanation] = useState('');
    const [impactCount, setImpactCount] = useState<number | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [resolvingBlockId, setResolvingBlockId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    const headers = useMemo(() => ({ Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' }), [accessToken]);

    const loadData = useCallback(async () => {
        if (!accessToken) return;
        const [providersResponse, blocksResponse, callsResponse] = await Promise.all([
            fetch('/api/appointments/providers', { headers }).then((r) => r.json()).catch(() => ({})),
            fetch('/api/emergency-blocks', { headers }).then((r) => r.json()).catch(() => ({})),
            fetch('/api/appointments/calls/all', { headers }).then((r) => r.json()).catch(() => ({})),
        ]);
        setProviders(providersResponse?.data?.providers || []);
        const fetchedBlocks: EmergencyBlock[] = blocksResponse?.data?.blocks || [];
        setBlocks(fetchedBlocks);

        // Map calls to their block using call_id pattern: emergency_{blockId}_
        const allCalls: any[] = callsResponse?.data || [];
        const callsByBlock: Record<string, any[]> = {};
        for (const block of fetchedBlocks) {
            callsByBlock[block.id] = allCalls.filter((c: any) =>
                c.callId?.startsWith(`emergency_${block.id}`) ||
                (c.summary && c.summary.includes('Emergency:'))
            );
        }
        setEmergencyCalls(callsByBlock);
    }, [accessToken, headers]);

    useEffect(() => {
        if (accessToken) {
            void loadData();
        }
    }, [accessToken, loadData]);

    useEffect(() => {
        const selected = BLOCK_TYPES.find((item) => item.key === blockType);
        if (!selected || blockType === 'custom') {
            setReason('');
            setAiExplanation('');
            return;
        }
        setReason(selected.reason);
        setAiExplanation(selected.aiPrompt);
    }, [blockType]);

    const isClinic = blockType === 'clinic';

    useEffect(() => {
        const needsProvider = !isClinic && !selectedProviderId;
        if (needsProvider || !startTime || !endTime || !accessToken) {
            setImpactCount(null);
            return;
        }
        if (new Date(endTime) <= new Date(startTime)) {
            setImpactCount(null);
            return;
        }

        const timer = setTimeout(() => {
            const params = new URLSearchParams({
                startTime: new Date(startTime).toISOString(),
                endTime: new Date(endTime).toISOString(),
            });
            if (!isClinic && selectedProviderId) params.set('providerId', selectedProviderId);
            fetch(`/api/emergency-blocks/impact?${params}`, { headers: { Authorization: `Bearer ${accessToken}` } })
                .then((response) => response.json())
                .then((data) => setImpactCount(data.data?.count ?? null))
                .catch(() => setImpactCount(null));
        }, 400);

        return () => clearTimeout(timer);
    }, [accessToken, endTime, isClinic, selectedProviderId, startTime]);

    const filteredProviders = providers.filter((provider) => {
        const query = providerSearch.toLowerCase();
        return !query || provider.name.toLowerCase().includes(query) || provider.specialty.toLowerCase().includes(query);
    });

    const activeBlocks = blocks.filter((block) => block.status === 'active');
    const resolvedBlocks = blocks.filter((block) => block.status === 'resolved');

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault();
        if ((!isClinic && !selectedProviderId) || !startTime || !endTime || !reason) {
            setError('Please fill in all required fields.');
            return;
        }
        if (new Date(endTime) <= new Date(startTime)) {
            setError('End time must be after start time.');
            return;
        }

        setIsLoading(true);
        setError(null);
        setSuccess(null);

        try {
            const response = await fetch('/api/emergency-blocks', {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    ...(isClinic ? {} : { providerId: selectedProviderId }),
                    startTime: new Date(startTime).toISOString(),
                    endTime: new Date(endTime).toISOString(),
                    reason,
                    aiExplanation: aiExplanation || reason,
                }),
            });
            const payload = await response.json();

            if (!response.ok) {
                setError(payload.error || 'Failed to create emergency block.');
                return;
            }

            setSuccess(`Emergency block activated. ${payload.data.affectedCount} appointment(s) affected — AI will call patients.`);
            setSelectedProviderId('');
            setProviderSearch('');
            setStartTime('');
            setEndTime('');
            setImpactCount(null);
            await loadData();
        } catch {
            setError('Connection error. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleResolve = async (blockId: string) => {
        if (!accessToken || resolvingBlockId) return;

        setResolvingBlockId(blockId);
        setError(null);
        setSuccess(null);

        try {
            const response = await fetch(`/api/emergency-blocks/${blockId}/resolve`, {
                method: 'PATCH',
                headers,
            });
            const payload = await response.json().catch(() => ({}));

            if (!response.ok) {
                setError(payload.error || 'Failed to resolve emergency block.');
                return;
            }

            setSuccess('Emergency block marked as resolved.');
            await loadData();
        } catch {
            setError('Connection error. Please try again.');
        } finally {
            setResolvingBlockId(null);
        }
    };

    const formatDateTime = (value: string) => parseApiDate(value).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
    });

    return (
        <div className={styles.page}>
            <SideNav />
            <main className={styles.main}>
                <header className={styles.header}>
                    <div>
                        <h1 className={styles.title}>Emergency Management</h1>
                        <p style={{ fontSize: '0.85rem', color: 'var(--text-3)', margin: 0 }}>Block availability — AI will auto-call all affected patients</p>
                    </div>
                    {activeBlocks.length > 0 && (
                        <div className={styles.activePill}>
                            <span className={styles.activeDot} />
                            {activeBlocks.length} Active Emergency
                        </div>
                    )}
                </header>

                <div className={styles.layout}>
                    <section className={styles.formShell}>
                        <div className={styles.formHeader}>
                            <AlertTriangle size={15} />
                            Create Emergency Block
                        </div>
                        <form className={styles.form} onSubmit={handleSubmit}>
                            {error && <div className={styles.errorBanner}><AlertTriangle size={14} />{error}</div>}
                            {success && <div className={styles.successBanner}><CheckCircle size={14} />{success}</div>}

                            <div className={styles.field}>
                                <span className={styles.label}>Block Type</span>
                                <div className={styles.typeGrid}>
                                    {BLOCK_TYPES.map((item) => (
                                        <button
                                            key={item.key}
                                            type="button"
                                            className={`${styles.typeButton} ${blockType === item.key ? styles.typeButtonActive : ''}`}
                                            onClick={() => setBlockType(item.key)}
                                        >
                                            {item.label}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {!isClinic && <div className={styles.field}>
                                <span className={styles.label}>Provider</span>
                                <div className={styles.dropdownWrap}>
                                    <input
                                        className={styles.input}
                                        placeholder="Search provider..."
                                        value={selectedProviderId
                                            ? `${providers.find((provider) => provider.id === selectedProviderId)?.name || ''} — ${providers.find((provider) => provider.id === selectedProviderId)?.specialty || ''}`
                                            : providerSearch}
                                        onChange={(event) => {
                                            setProviderSearch(event.target.value);
                                            setSelectedProviderId('');
                                            setDropdownOpen(true);
                                        }}
                                        onFocus={() => setDropdownOpen(true)}
                                        onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
                                    />
                                    {dropdownOpen && !selectedProviderId && filteredProviders.length > 0 && (
                                        <div className={styles.dropdown}>
                                            {filteredProviders.map((provider) => (
                                                <button
                                                    key={provider.id}
                                                    type="button"
                                                    className={styles.dropdownItem}
                                                    onMouseDown={() => {
                                                        setSelectedProviderId(provider.id);
                                                        setProviderSearch('');
                                                        setDropdownOpen(false);
                                                    }}
                                                >
                                                    <span className={styles.dropdownName}>{provider.name}</span>
                                                    <span className={styles.dropdownMeta}>{provider.specialty}</span>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>}

                            <div className={styles.dateRow}>
                                <div className={styles.field}>
                                    <span className={styles.label}>From</span>
                                    <input className={styles.input} type="datetime-local" value={startTime} onChange={(event) => setStartTime(event.target.value)} />
                                </div>
                                <div className={styles.field}>
                                    <span className={styles.label}>To</span>
                                    <input className={styles.input} type="datetime-local" value={endTime} onChange={(event) => setEndTime(event.target.value)} />
                                </div>
                            </div>

                            <div className={styles.field}>
                                <span className={styles.label}>Reason</span>
                                <input className={styles.input} type="text" value={reason} onChange={(event) => setReason(event.target.value)} />
                            </div>

                            <div className={styles.field}>
                                <span className={styles.label}>AI Message</span>
                                <textarea className={styles.textarea} rows={4} value={aiExplanation} onChange={(event) => setAiExplanation(event.target.value)} />
                            </div>

                            {impactCount !== null && (
                                <div className={styles.impactBanner}>
                                    <AlertTriangle size={14} />
                                    <span>
                                        <strong>{impactCount} appointments</strong> will be affected. AI will call all patients.
                                    </span>
                                </div>
                            )}

                            <button type="submit" className={styles.submitButton} disabled={isLoading}>
                                {isLoading ? 'Creating…' : 'Create Emergency Block'}
                            </button>
                        </form>
                    </section>

                    <section className={styles.blocksColumn}>
                        {activeBlocks.length > 0 && (
                            <div className={styles.section}>
                                <div className={styles.sectionLabel}>Active Blocks</div>
                                <div className={styles.blockList}>
                                    {activeBlocks.map((block) => (
                                        <article key={block.id} className={`${styles.blockCard} ${styles.blockCardActive}`}>
                                            <div className={styles.blockHeader}>
                                                <div className={styles.blockHeaderCopy}>
                                                    <span className={styles.blockTitle}>
                                                        {block.provider_name ? `${block.provider_name} — ${block.reason}` : block.reason}
                                                    </span>
                                                    <span className={styles.blockStatus}>active</span>
                                                </div>
                                                <button
                                                    type="button"
                                                    className={styles.resolveButton}
                                                    onClick={() => void handleResolve(block.id)}
                                                    disabled={resolvingBlockId === block.id}
                                                >
                                                    {resolvingBlockId === block.id ? 'Resolving…' : 'Resolve'}
                                                </button>
                                            </div>
                                            <div className={styles.blockMeta}><Clock size={12} />{formatDateTime(block.start_time)} → {formatDateTime(block.end_time)}</div>
                                            {block.ai_explanation && <div className={styles.blockNote}>{block.ai_explanation}</div>}

                                            {/* Calls Placed */}
                                            <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: 10 }}>
                                                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>
                                                    Calls Placed ({(emergencyCalls[block.id] || []).length})
                                                </div>
                                                {(emergencyCalls[block.id] || []).length === 0 ? (
                                                    <div style={{ fontSize: 12, color: 'var(--text-3)' }}>No calls placed — 0 appointments were affected</div>
                                                ) : (
                                                    (emergencyCalls[block.id] || []).map((call: any) => (
                                                        <div key={call.callId} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                                            {call.outcome === 'confirmed' ? <Phone size={13} color="#22c55e" /> : call.status === 'ended' ? <PhoneMissed size={13} color="#f59e0b" /> : <PhoneOff size={13} color="#ef4444" />}
                                                            <div style={{ flex: 1 }}>
                                                                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>{call.patientName || call.patientPhone}</div>
                                                                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{call.patientPhone}</div>
                                                            </div>
                                                            <div style={{ fontSize: 11, color: call.status === 'ended' ? '#22c55e' : '#f59e0b' }}>
                                                                {call.status === 'ended' ? 'Answered' : call.status === 'in-progress' ? 'Calling...' : 'No answer'}
                                                            </div>
                                                        </div>
                                                    ))
                                                )}
                                            </div>
                                        </article>
                                    ))}
                                </div>
                            </div>
                        )}

                        {resolvedBlocks.length > 0 && (
                            <div className={styles.section}>
                                <div className={`${styles.sectionLabel} ${styles.sectionLabelMuted}`}><XCircle size={13} />Resolved</div>
                                <div className={styles.blockList}>
                                    {resolvedBlocks.map((block) => (
                                        <article key={block.id} className={`${styles.blockCard} ${styles.blockCardResolved}`}>
                                            <div className={styles.blockHeader}>
                                                <span className={styles.blockTitle}>
                                                    {block.provider_name ? `${block.provider_name} — ${block.reason}` : block.reason}
                                                </span>
                                                <span className={styles.blockStatusMuted}>resolved</span>
                                            </div>
                                            <div className={styles.blockMeta}><Clock size={12} />{formatDateTime(block.start_time)} → {formatDateTime(block.end_time)}</div>
                                        </article>
                                    ))}
                                </div>
                            </div>
                        )}

                        {blocks.length === 0 && (
                            <div className={styles.emptyBlocks}>
                                <ShieldAlert size={32} />
                                <p>No emergency blocks</p>
                            </div>
                        )}
                    </section>
                </div>
            </main>
        </div>
    );
}
