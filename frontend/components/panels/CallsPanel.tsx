'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { ChevronDown, Search } from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { DateRangeFilter, DEFAULT_DATE_RANGE, inDateRange, type DateRangeValue } from '@/components/DateRangeFilter/DateRangeFilter';
import styles from '@/app/calls/calls.module.css';

interface CallRecord {
    patientName?: string;
    phone?: string;
    email?: string | null;
    callId: string;
    outcome: 'confirmed' | 'cancelled' | 'reschedule_requested' | 'no_answer' | 'voicemail' | 'failed' | 'call_failed' | 'info' | null;
    summary: string | null;
    transcript: string | null;
    durationSeconds: number | null;
    status: string;
    createdAt: string;
    appointmentId?: string;
    serviceName?: string;
    providerName?: string;
    appointmentDate?: string;
    recordingUrl?: string;
}

interface CallGroup {
    key: string;
    name: string;
    phone?: string;
    email?: string | null;
    calls: CallRecord[];
}

// Mirrors the dashboard's NOT_ANSWERED set (app/dashboard/page.tsx) — an
// outcome in this set means the lead was never actually reached.
const NOT_ANSWERED = new Set(['no_answer', 'voicemail', 'failed', 'call_failed']);

const OUTCOME_META = {
    confirmed: { label: 'Confirmed', className: styles.outcomeConfirmed },
    reschedule_requested: { label: 'Rescheduled', className: styles.outcomeRescheduled },
    no_answer: { label: 'No answer', className: styles.outcomeNeutral },
    voicemail: { label: 'Voicemail', className: styles.outcomeNeutral },
    cancelled: { label: 'Cancelled', className: styles.outcomeCancelled },
    failed: { label: 'Failed', className: styles.outcomeCancelled },
    call_failed: { label: 'Failed', className: styles.outcomeCancelled },
    info: { label: 'Information', className: styles.outcomeNeutral },
};

type CallFilter = 'all' | 'confirmed' | 'reschedule_requested' | 'no_answer' | 'voicemail' | 'cancelled' | 'picked_up';

// ?outcome= on the URL drives the initial filter — this is what lets the
// dashboard's tiles ("Picked-Up Calls", "Voicemails") link straight to a
// pre-filtered view instead of dumping the user on the unfiltered list.
const VALID_OUTCOME_PARAMS = new Set<CallFilter>(['confirmed', 'reschedule_requested', 'no_answer', 'voicemail', 'cancelled', 'picked_up']);

function formatDate(iso: string) {
    // The API returns naive timestamps with no timezone marker (the DB
    // stores/returns plain UTC wall-clock now, but psycopg2's naive
    // datetime objects serialize without a trailing 'Z' or offset).
    // Without this, new Date() falls back to parsing the string as
    // browser-local time per the ECMAScript spec — confirmed live, a call
    // that had just ended displayed as roughly 12 hours in the past.
    const hasTzMarker = /Z$|[+-]\d{2}:?\d{2}$/.test(iso);
    const date = new Date(hasTzMarker ? iso : `${iso}Z`);
    return {
        day: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
        time: date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }),
    };
}

function formatDuration(seconds: number | null) {
    if (!seconds) return '—';
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    return `${minutes}m ${remainder}s`;
}

function CallDetailPanel({ call }: { call: CallRecord }) {
    return (
        <div className={styles.expandedPanel}>
            <div className={styles.panelHeader}>
                <div className={styles.panelTitle}>Call Details</div>
            </div>
            {call.recordingUrl && (
                // Never link call.recordingUrl directly — it's the raw Azure
                // blob URL, and that storage account has public access
                // disabled (confirmed live: clicking it renders Azure's own
                // "PublicAccessNotPermitted" XML error page). Always go
                // through our own /api/calls/{callId}/recording proxy, same
                // as the lead detail page's player.
                <audio controls style={{ width: '100%', height: 32, marginTop: 4, marginBottom: 12 }}>
                    <source src={`/api/calls/${call.callId}/recording`} />
                </audio>
            )}

            {call.summary && (
                <div className={styles.summarySection}>
                    <div className={styles.sectionLabel}>AI Summary</div>
                    <p className={styles.summaryText}>{call.summary}</p>
                </div>
            )}

            {call.transcript && (
                <div className={styles.transcriptSection}>
                    <div className={styles.sectionLabel}>Transcript</div>
                    <div className={styles.transcriptFlow}>
                        {call.transcript.split('\n').filter(l => l.trim()).map((line, idx) => {
                            const isAi = line.toLowerCase().startsWith('ai:');
                            const isPatient = line.toLowerCase().startsWith('patient:');
                            const content = line.replace(/^(Ai|Patient):\s*/i, '');

                            return (
                                <div key={idx} className={`${styles.chatRow} ${isAi ? styles.chatAi : isPatient ? styles.chatPatient : ''}`}>
                                    <div className={styles.chatAvatar}>
                                        {isAi ? 'AI' : 'P'}
                                    </div>
                                    <div className={styles.chatBubble}>
                                        {content}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

export function CallsPanel({ embedded = false }: { embedded?: boolean } = {}) {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { isAuthenticated, accessToken, isLoading: authLoading } = useAuth();
    const [calls, setCalls] = useState<CallRecord[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [expandedId, setExpandedId] = useState<string | null>(null);
    const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
    const initialOutcome = searchParams.get('outcome');
    const [filter, setFilter] = useState<CallFilter>(
        VALID_OUTCOME_PARAMS.has(initialOutcome as CallFilter) ? (initialOutcome as CallFilter) : 'all'
    );
    const [search, setSearch] = useState('');
    const [dateRange, setDateRange] = useState<DateRangeValue>(DEFAULT_DATE_RANGE);

    useEffect(() => {
        if (!authLoading && !isAuthenticated) {
            router.push('/login');
        }
    }, [authLoading, isAuthenticated, router]);

    const fetchCalls = useCallback(async () => {
        if (!accessToken) return;
        setIsLoading(true);
        try {
            const response = await fetch('/api/crm/calls', {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            const payload = await response.json();
            setCalls(payload.data?.calls || payload.data || []);
        } catch {
            setCalls([]);
        } finally {
            setIsLoading(false);
        }
    }, [accessToken]);

    useEffect(() => {
        if (accessToken) {
            void fetchCalls();
        }
    }, [accessToken, fetchCalls]);

    const displayed = calls.filter((call) => {
        if (filter === 'picked_up') {
            if (NOT_ANSWERED.has(call.outcome || '')) return false;
        } else if (filter !== 'all' && call.outcome !== filter) {
            return false;
        }
        if (!inDateRange(call.createdAt, dateRange)) return false;
        const q = search.trim().toLowerCase();
        if (!q) return true;
        const haystack = `${call.patientName || ''} ${call.email || ''} ${call.phone || ''}`.toLowerCase();
        return haystack.includes(q);
    });

    const groups = useMemo(() => {
        const map = new Map<string, CallGroup>();
        for (const call of displayed) {
            const key = call.phone && call.phone !== '—' ? call.phone : (call.patientName || call.callId);
            let group = map.get(key);
            if (!group) {
                group = { key, name: call.patientName || call.phone || 'Unknown', phone: call.phone, email: call.email, calls: [] };
                map.set(key, group);
            }
            if (!group.email && call.email) group.email = call.email;
            group.calls.push(call);
        }
        return Array.from(map.values());
    }, [displayed]);

    const toggleGroup = (key: string) => {
        setExpandedId(null);
        setExpandedGroup((current) => (current === key ? null : key));
    };

    const stats = [
        { label: 'Total calls', value: calls.length, className: styles.statPrimary },
        { label: 'Confirmed', value: calls.filter((call) => call.outcome === 'confirmed').length, className: styles.statPrimary },
        { label: 'Rescheduled', value: calls.filter((call) => call.outcome === 'reschedule_requested').length, className: styles.statWarning },
        { label: 'No answer', value: calls.filter((call) => call.outcome === 'no_answer' || call.outcome === 'voicemail').length, className: styles.statMuted },
    ];

    if (authLoading && !embedded) {
        return (
            <div className={styles.loadingScreen}>
                <div className={styles.spinner} />
                <p>Loading call history…</p>
            </div>
        );
    }

    const content = (
        <>
                {!embedded && (
                    <div className={styles.header}>
                        <div>
                            <h1 className={styles.title}>Communication Log</h1>
                            <p className={styles.subtitle}>Review AI call transcripts and patient outcomes</p>
                        </div>
                    </div>
                )}

                <div className={styles.statsGrid}>
                    {stats.map((stat) => (
                        <div key={stat.label} className={styles.statCard}>
                            <div className={`${styles.statValue} ${stat.className}`}>{stat.value}</div>
                            <div className={styles.statLabel}>{stat.label}</div>
                        </div>
                    ))}
                </div>

                <div className={styles.filters}>
                    <div className={styles.filterPills}>
                        {[
                            ['all', 'All'],
                            ['picked_up', 'Picked up'],
                            ['confirmed', 'Confirmed'],
                            ['reschedule_requested', 'Rescheduled'],
                            ['no_answer', 'No answer'],
                            ['voicemail', 'Voicemail'],
                            ['cancelled', 'Cancelled'],
                        ].map(([value, label]) => (
                            <button
                                key={value}
                                type="button"
                                className={`${styles.filterPill} ${filter === value ? styles.filterPillActive : ''}`}
                                onClick={() => setFilter(value as typeof filter)}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        <div className={styles.searchBox}>
                            <Search size={13} />
                            <input
                                type="text"
                                placeholder="Search by name, email or phone..."
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                            />
                        </div>
                        <DateRangeFilter value={dateRange} onChange={setDateRange} />
                    </div>
                </div>

                <section className={styles.tableShell}>
                    <div className={styles.tableHeader}>
                        <div>Caller</div>
                        <div>Service / Provider</div>
                        <div>Date &amp; Time</div>
                        <div>Outcome</div>
                        <div>Duration</div>
                        <div />
                    </div>

                    {isLoading ? (
                        <div className={styles.emptyState}>Loading call history…</div>
                    ) : groups.length === 0 ? (
                        <div className={styles.emptyState}>No calls in this view.</div>
                    ) : (
                        groups.map((group) => {
                            const latest = group.calls[0];
                            const isSingle = group.calls.length === 1;
                            const outcome = latest.outcome ? (OUTCOME_META[latest.outcome] ?? OUTCOME_META.info) : OUTCOME_META.info;
                            const { day, time } = formatDate(latest.createdAt);
                            const isGroupOpen = isSingle ? expandedId === latest.callId : expandedGroup === group.key;

                            const handleHeaderClick = () => {
                                if (isSingle) {
                                    setExpandedGroup(null);
                                    setExpandedId((current) => (current === latest.callId ? null : latest.callId));
                                } else {
                                    toggleGroup(group.key);
                                }
                            };

                            return (
                                <div key={group.key} className={styles.rowBlock}>
                                    <button
                                        type="button"
                                        className={styles.tableRow}
                                        onClick={handleHeaderClick}
                                    >
                                        <div>
                                            <div className={styles.primaryText}>{group.name}</div>
                                            <div className={styles.secondaryText}>
                                                {group.phone && group.phone !== '—' ? group.phone : (isSingle ? latest.callId : `${group.calls.length} calls`)}
                                            </div>
                                            {group.email && <div className={styles.secondaryText}>{group.email}</div>}
                                        </div>
                                        <div>
                                            <div className={styles.rowText}>{latest.serviceName || '—'}</div>
                                            {!isSingle && (
                                                <div className={styles.secondaryText}>{group.calls.length} calls total</div>
                                            )}
                                        </div>
                                        <div>
                                            <div className={styles.rowText}>{day}</div>
                                            <div className={styles.secondaryText}>{time}{!isSingle ? ' (latest)' : ''}</div>
                                        </div>
                                        <div>
                                            <span className={`${styles.outcomeBadge} ${outcome.className}`}>{outcome.label}</span>
                                        </div>
                                        <div className={styles.duration}>{formatDuration(latest.durationSeconds)}</div>
                                        <div className={styles.chevronCell}>
                                            <ChevronDown size={16} className={isGroupOpen ? styles.chevronOpen : ''} />
                                        </div>
                                    </button>

                                    {isSingle ? (
                                        isGroupOpen && <CallDetailPanel call={latest} />
                                    ) : (
                                        isGroupOpen && (
                                            <div className={styles.groupChildren}>
                                                {group.calls.map((call) => {
                                                    const callOutcome = call.outcome ? (OUTCOME_META[call.outcome] ?? OUTCOME_META.info) : OUTCOME_META.info;
                                                    const callDate = formatDate(call.createdAt);
                                                    const isCallOpen = expandedId === call.callId;
                                                    return (
                                                        <div key={call.callId} className={styles.childBlock}>
                                                            <button
                                                                type="button"
                                                                className={`${styles.tableRow} ${styles.childRow}`}
                                                                onClick={() => setExpandedId(isCallOpen ? null : call.callId)}
                                                            >
                                                                <div>
                                                                    <div className={styles.rowText}>{call.callId}</div>
                                                                </div>
                                                                <div>
                                                                    <div className={styles.rowText}>{call.serviceName || '—'}</div>
                                                                    <div className={styles.secondaryText}>{call.providerName || (call.appointmentId ? `Appointment ${call.appointmentId}` : call.status)}</div>
                                                                </div>
                                                                <div>
                                                                    <div className={styles.rowText}>{callDate.day}</div>
                                                                    <div className={styles.secondaryText}>{callDate.time}</div>
                                                                </div>
                                                                <div>
                                                                    <span className={`${styles.outcomeBadge} ${callOutcome.className}`}>{callOutcome.label}</span>
                                                                </div>
                                                                <div className={styles.duration}>{formatDuration(call.durationSeconds)}</div>
                                                                <div className={styles.chevronCell}>
                                                                    <ChevronDown size={16} className={isCallOpen ? styles.chevronOpen : ''} />
                                                                </div>
                                                            </button>

                                                            {isCallOpen && <CallDetailPanel call={call} />}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )
                                    )}
                                </div>
                            );
                        })
                    )}
                </section>
        </>
    );

    if (embedded) return content;

    return (
        <div className={styles.page}>
            <SideNav />
            <main className={styles.main}>{content}</main>
        </div>
    );
}
