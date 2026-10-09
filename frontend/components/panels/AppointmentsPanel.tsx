'use client';

import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { RefreshCw, List, CalendarDays, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { DateRangeFilter, DEFAULT_DATE_RANGE, inDateRange, type DateRangeValue } from '@/components/DateRangeFilter/DateRangeFilter';
import styles from '@/app/appointments/appointments.module.css';

interface Appointment {
    id: string;
    start_time: string;
    end_time: string;
    service_name?: string;
    provider_name?: string;
    status: string;
    notes?: string;
    first_name?: string;
    last_name?: string;
    patient_email?: string;
    patient_phone?: string;
}

interface CalendarSyncMetadata {
    status: 'success' | 'failed' | 'skipped';
    attempts: number;
    error: string | null;
}

function formatAppointment(iso: string) {
    const date = new Date(iso);
    return {
        date: date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }),
        time: date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }),
        isPast: date.getTime() < Date.now(),
    };
}

function buildCalendarNotice(prefix: string, calendarSync?: CalendarSyncMetadata) {
    if (!calendarSync) return prefix;
    if (calendarSync.status === 'success') return `${prefix} Google Calendar synced.`;
    if (calendarSync.status === 'failed') return `${prefix} Google Calendar sync failed after ${calendarSync.attempts} attempts.`;
    if (calendarSync.status === 'skipped') return `${prefix} Google Calendar was not connected.`;
    return prefix;
}

function statusTone(status: string) {
    if (status === 'confirmed') return styles.statusConfirmed;
    if (status === 'cancelled') return styles.statusCancelled;
    return styles.statusPending;
}

function PillButton({
    children,
    active = false,
    onClick,
}: {
    children: ReactNode;
    active?: boolean;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            className={`${styles.filterPill} ${active ? styles.filterPillActive : ''}`}
            onClick={onClick}
        >
            {children}
        </button>
    );
}

const DAYS_SHORT   = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const MONTHS_LONG  = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function CalendarView({ appointments, onReschedule }: { appointments: Appointment[]; onReschedule: (a: Appointment) => void }) {
    const [viewDate, setViewDate] = useState(new Date());
    const year  = viewDate.getFullYear();
    const month = viewDate.getMonth();
    const firstDay    = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = new Date();

    const byDay: Record<number, Appointment[]> = {};
    appointments.forEach(a => {
        const d = new Date(a.start_time);
        if (d.getFullYear() === year && d.getMonth() === month) {
            const day = d.getDate();
            if (!byDay[day]) byDay[day] = [];
            byDay[day].push(a);
        }
    });

    const cells: (number | null)[] = [...Array(firstDay).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)];
    while (cells.length % 7 !== 0) cells.push(null);

    const [selectedDay, setSelectedDay] = useState<number | null>(null);
    const selectedAppts = selectedDay ? (byDay[selectedDay] || []) : [];

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 20, marginTop: 16 }}>
            <div style={{ background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 18px', borderBottom: '1px solid var(--border)' }}>
                    <button onClick={() => setViewDate(new Date(year, month - 1, 1))} style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 8, padding: '4px 8px', cursor: 'pointer', color: 'var(--text-1)' }}>
                        <ChevronLeft size={15} />
                    </button>
                    <span style={{ fontWeight: 700, fontSize: 15 }}>{MONTHS_LONG[month]} {year}</span>
                    <button onClick={() => setViewDate(new Date(year, month + 1, 1))} style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 8, padding: '4px 8px', cursor: 'pointer', color: 'var(--text-1)' }}>
                        <ChevronRight size={15} />
                    </button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', padding: '8px 12px 4px', gap: 2 }}>
                    {DAYS_SHORT.map(d => <div key={d} style={{ textAlign: 'center', fontSize: 11, fontWeight: 700, color: 'var(--text-4)', padding: '4px 0' }}>{d}</div>)}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', padding: '0 12px 12px', gap: 3 }}>
                    {cells.map((day, i) => {
                        if (!day) return <div key={`e-${i}`} />;
                        const isToday    = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
                        const isSelected = selectedDay === day;
                        const appts      = byDay[day] || [];
                        const hasAppts = appts.length > 0;
                        return (
                            <div key={day} onClick={() => setSelectedDay(isSelected ? null : day)}
                                style={{ borderRadius: 8, padding: '5px 3px', textAlign: 'center', cursor: 'pointer',
                                    background: isSelected ? 'var(--primary)' : isToday ? 'rgba(185, 134, 42,0.1)' : hasAppts ? 'rgba(185, 134, 42,0.06)' : 'transparent',
                                    border: `1px solid ${isToday && !isSelected ? 'var(--primary)' : hasAppts && !isSelected ? 'rgba(185, 134, 42,0.3)' : 'transparent'}`,
                                    color: isSelected ? '#fff' : 'var(--text-1)', fontWeight: isToday || isSelected || hasAppts ? 700 : 400 }}>
                                <div style={{ fontSize: 13 }}>{day}</div>
                                {hasAppts && (
                                    <div style={{ display: 'flex', justifyContent: 'center', gap: 3, marginTop: 3 }}>
                                        {appts.slice(0,3).map(a => (
                                            <div key={a.id} style={{ width: 7, height: 7, borderRadius: '50%', background: isSelected ? '#fff' : (a.status === 'confirmed' ? '#10b981' : a.status === 'cancelled' ? '#ef4444' : '#f59e0b') }} />
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
            <div style={{ background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: 12, padding: 16, overflowY: 'auto' }}>
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 12 }}>
                    {selectedDay ? `${MONTHS_LONG[month]} ${selectedDay}` : 'Select a day'}
                </div>
                {!selectedDay && <p style={{ color: 'var(--text-4)', fontSize: 13 }}>Click a day to view appointments</p>}
                {selectedDay && selectedAppts.length === 0 && <p style={{ color: 'var(--text-4)', fontSize: 13 }}>No appointments</p>}
                {selectedAppts.map(a => {
                    const t = new Date(a.start_time).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                    const sc = statusTone(a.status);
                    return (
                        <div key={a.id} style={{ background: 'var(--bg-elevated,#1a1a1a)', border: '1px solid var(--border)', borderRadius: 10, padding: '12px', marginBottom: 10 }}>
                            <div style={{ fontSize: 11, color: 'var(--text-4)', marginBottom: 3 }}>{t}</div>
                            <div style={{ fontWeight: 600, fontSize: 14 }}>{a.service_name || 'Appointment'}</div>
                            {a.provider_name && <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 2 }}>With {a.provider_name}</div>}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 }}>
                                <span className={`${sc}`} style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20 }}>{a.status}</span>
                                {a.status !== 'cancelled' && new Date(a.start_time).getTime() > Date.now() && (
                                    <button onClick={() => onReschedule(a)} style={{ fontSize: 11, padding: '3px 8px', background: 'none', border: '1px solid var(--border)', borderRadius: 6, cursor: 'pointer', color: 'var(--text-1)' }}>Reschedule</button>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export function AppointmentsPanel({ embedded = false }: { embedded?: boolean } = {}) {
    const router = useRouter();
    const { isAuthenticated, accessToken, isLoading: authLoading, isLoggingOut } = useAuth();

    const [appointments, setAppointments] = useState<Appointment[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState('');
    const [view,   setView]   = useState<'list' | 'calendar'>('list');
    const [filter, setFilter] = useState<'all' | 'upcoming' | 'past'>('all');
    const [search, setSearch] = useState('');
    const [dateRange, setDateRange] = useState<DateRangeValue>(DEFAULT_DATE_RANGE);
    const [cancellingId, setCancellingId] = useState<string | null>(null);
    const [rescheduleId, setRescheduleId] = useState<string | null>(null);
    const [rescheduleDate, setRescheduleDate] = useState('');
    const [rescheduleTime, setRescheduleTime] = useState('');
    const [savingReschedule, setSavingReschedule] = useState(false);

    useEffect(() => {
        if (!authLoading && !isAuthenticated && !isLoggingOut) {
            router.push('/login');
        }
    }, [authLoading, isAuthenticated, isLoggingOut, router]);

    const fetchAppointments = useCallback(async () => {
        if (!accessToken) return;
        setIsLoading(true);
        setError(null);

        try {
            const response = await fetch('/api/appointments?includeCancelled=true', {
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                    'Content-Type': 'application/json',
                },
            });

            if (response.ok) {
                const payload = await response.json();
                setAppointments(payload.data?.appointments || []);
                return;
            }

            if (response.status === 401) {
                router.push('/login');
                return;
            }

            setError('Failed to load appointments.');
        } catch {
            setError('Unable to connect to the server.');
        } finally {
            setIsLoading(false);
        }
    }, [accessToken, router]);

    useEffect(() => {
        if (accessToken) {
            void fetchAppointments();
        }
    }, [accessToken, fetchAppointments]);


    const [confirmingId, setConfirmingId] = useState<string | null>(null);

    const handleConfirm = async (appointmentId: string) => {
        if (!accessToken || confirmingId) return;
        setConfirmingId(appointmentId);
        try {
            const response = await fetch(`/api/appointments/${appointmentId}`, {
                method: 'PUT',
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ status: 'confirmed' }),
            });
            if (!response.ok) {
                setError('Failed to confirm appointment.');
                return;
            }
            setNotice('Appointment confirmed.');
            await fetchAppointments();
        } catch {
            setError('Unable to confirm appointment.');
        } finally {
            setConfirmingId(null);
        }
    };

    const handleCancel = async (appointmentId: string) => {
        if (!accessToken || cancellingId) return;
        if (!confirm('Are you sure you want to cancel this appointment?')) return;

        setCancellingId(appointmentId);
        try {
            const response = await fetch(`/api/appointments/${appointmentId}`, {
                method: 'DELETE',
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                    'Content-Type': 'application/json',
                },
            });
            const payload = await response.json().catch(() => null);

            if (!response.ok) {
                setError(payload?.error || 'Failed to cancel appointment.');
                return;
            }

            const calendarSync = payload?.data?.calendarSync as CalendarSyncMetadata | undefined;
            setNotice(buildCalendarNotice('Appointment cancelled.', calendarSync));
            await fetchAppointments();
        } catch {
            setError('Unable to cancel appointment.');
        } finally {
            setCancellingId(null);
        }
    };

    const openRescheduleModal = (appointment: Appointment) => {
        const date = new Date(appointment.start_time);
        setRescheduleId(appointment.id);
        setRescheduleDate(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`);
        setRescheduleTime(`${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`);
    };

    const closeRescheduleModal = (force = false) => {
        if (savingReschedule && !force) return;
        setRescheduleId(null);
        setRescheduleDate('');
        setRescheduleTime('');
    };

    const handleRescheduleSubmit = async () => {
        if (!accessToken || !rescheduleId || !rescheduleDate || !rescheduleTime) return;
        setSavingReschedule(true);
        setError(null);

        try {
            const response = await fetch(`/api/appointments/${rescheduleId}`, {
                method: 'PUT',
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    startTime: new Date(`${rescheduleDate}T${rescheduleTime}:00`).toISOString(),
                }),
            });
            const payload = await response.json().catch(() => null);

            if (!response.ok) {
                setError(payload?.error || 'Failed to reschedule appointment.');
                return;
            }

            const calendarSync = payload?.data?.calendarSync as CalendarSyncMetadata | undefined;
            setNotice(buildCalendarNotice('Appointment rescheduled.', calendarSync));
            closeRescheduleModal(true);
            await fetchAppointments();
        } catch {
            setError('Unable to reschedule appointment.');
        } finally {
            setSavingReschedule(false);
        }
    };

    const upcoming = useMemo(() => {
        return appointments
            .filter((appointment) => new Date(appointment.start_time).getTime() >= Date.now() && appointment.status !== 'cancelled')
            .sort((left, right) => new Date(left.start_time).getTime() - new Date(right.start_time).getTime());
    }, [appointments]);

    const past = useMemo(() => {
        return appointments
            .filter((appointment) => new Date(appointment.start_time).getTime() < Date.now() || appointment.status === 'cancelled')
            .sort((left, right) => new Date(right.start_time).getTime() - new Date(left.start_time).getTime());
    }, [appointments]);

    const nextAppointment = upcoming[0] || null;
    const displayed = useMemo(() => {
        const base = filter === 'upcoming' ? upcoming : filter === 'past' ? past : [...upcoming, ...past];
        const q = search.trim().toLowerCase();
        return base.filter((appointment) => {
            if (!inDateRange(appointment.start_time, dateRange)) return false;
            if (!q) return true;
            const clientName = [appointment.first_name, appointment.last_name].filter(Boolean).join(' ');
            const haystack = `${clientName} ${appointment.patient_email || ''} ${appointment.patient_phone || ''}`.toLowerCase();
            return haystack.includes(q);
        });
    }, [filter, past, upcoming, search, dateRange]);

    if (authLoading && !embedded) {
        return (
            <div className={styles.loadingScreen}>
                <div className={styles.spinner} />
                <p>Loading appointments…</p>
            </div>
        );
    }

    const content = (
        <>
                <div className={styles.header}>
                    <div>
                        {!embedded && <h1 className={styles.title}>Appointments</h1>}
                        <p className={styles.subtitle}>{upcoming.length} upcoming · {past.length} past</p>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <div style={{ display: 'flex', background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
                            <button type="button" onClick={() => setView('list')}
                                style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 13px', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
                                    background: view === 'list' ? 'var(--primary)' : 'transparent',
                                    color: view === 'list' ? '#fff' : 'var(--text-2)' }}>
                                <List size={14} /> List
                            </button>
                            <button type="button" onClick={() => setView('calendar')}
                                style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 13px', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
                                    background: view === 'calendar' ? 'var(--primary)' : 'transparent',
                                    color: view === 'calendar' ? '#fff' : 'var(--text-2)' }}>
                                <CalendarDays size={14} /> Calendar
                            </button>
                        </div>
                        <button type="button" className={styles.primaryButton} onClick={() => router.push('/book')}>
                            + Book Appointment
                        </button>
                    </div>
                </div>

                {error && <div className={styles.errorBanner}>{error}</div>}
                {notice && <div className={styles.noticeBanner}>{notice}</div>}

                {nextAppointment && (() => {
                    const { date, time } = formatAppointment(nextAppointment.start_time);
                    return (
                        <section className={styles.nextBanner}>
                            <div className={styles.nextDot} />
                            <div className={styles.nextCopy}>
                                <span className={styles.nextLabel}>Next appointment</span>
                                <div className={styles.nextTitle}>{nextAppointment.service_name || 'Appointment'}{nextAppointment.provider_name ? ` — ${nextAppointment.provider_name}` : ''}</div>
                            </div>
                            <div className={styles.nextMeta}>{date} · {time}</div>
                            <button type="button" className={styles.secondaryButton} onClick={() => openRescheduleModal(nextAppointment)}>
                                Reschedule
                            </button>
                        </section>
                    );
                })()}

                {view === 'calendar' ? (
                    <CalendarView appointments={appointments} onReschedule={openRescheduleModal} />
                ) : (<>

                <div className={styles.controls}>
                    <div className={styles.filterGroup}>
                        <PillButton active={filter === 'all'} onClick={() => setFilter('all')}>All</PillButton>
                        <PillButton active={filter === 'upcoming'} onClick={() => setFilter('upcoming')}>Upcoming</PillButton>
                        <PillButton active={filter === 'past'} onClick={() => setFilter('past')}>Past</PillButton>
                    </div>
                    <div className={styles.filterGroup}>
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
                        <button type="button" className={styles.iconButton} onClick={() => void fetchAppointments()} disabled={isLoading}>
                            <RefreshCw size={15} className={isLoading ? styles.spinning : ''} />
                        </button>
                    </div>
                </div>

                <section className={styles.cardShell}>
                    {displayed.length > 0 ? (
                            <>
                                <div className={styles.tableHeader}>
                                    <div>Service</div>
                                    <div>Name</div>
                                    <div>Email</div>
                                    <div>Provider</div>
                                    <div>Date &amp; Time</div>
                                    <div>Status</div>
                                    <div />
                                </div>
                                {displayed.map((appointment) => {
                                    const { date, time, isPast } = formatAppointment(appointment.start_time);
                                    const clientName = [appointment.first_name, appointment.last_name].filter(Boolean).join(' ') || '—';
                                    return (
                                        <div key={appointment.id} className={styles.tableRow}>
                                            <div>
                                                <div className={styles.serviceName}>{appointment.service_name || 'Appointment'}</div>
                                                {appointment.notes && <div className={styles.rowSubtle}>{appointment.notes}</div>}
                                            </div>
                                            <div>
                                                <div className={styles.rowText}>{clientName}</div>
                                                {appointment.patient_phone && <div className={styles.rowSubtle}>{appointment.patient_phone}</div>}
                                            </div>
                                            <div>
                                                <div className={styles.rowText}>{appointment.patient_email || '—'}</div>
                                            </div>
                                            <div>
                                                <div className={styles.rowText}>{appointment.provider_name || '—'}</div>
                                            </div>
                                            <div>
                                                <div className={styles.rowText}>{date}</div>
                                                <div className={styles.rowSubtle}>{time}</div>
                                            </div>
                                            <div>
                                                <span className={`${styles.statusBadge} ${statusTone(appointment.status)}`}>{appointment.status}</span>
                                            </div>
                                            <div className={styles.rowActions}>
                                                {!isPast && appointment.status !== 'cancelled' && (
                                                    <>
                                                        {appointment.status === 'pending' && (
                                                            <button
                                                                type="button"
                                                                className={`${styles.rowButton} ${styles.rowButtonConfirm}`}
                                                                onClick={() => void handleConfirm(appointment.id)}
                                                                disabled={confirmingId === appointment.id}
                                                            >
                                                                {confirmingId === appointment.id ? '…' : 'Confirm'}
                                                            </button>
                                                        )}
                                                        <button type="button" className={styles.rowButton} onClick={() => openRescheduleModal(appointment)}>
                                                            Reschedule
                                                        </button>
                                                        <button
                                                            type="button"
                                                            className={`${styles.rowButton} ${styles.rowButtonDanger}`}
                                                            onClick={() => void handleCancel(appointment.id)}
                                                            disabled={cancellingId === appointment.id}
                                                        >
                                                            {cancellingId === appointment.id ? '…' : '×'}
                                                        </button>
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </>
                    ) : (
                        <div className={styles.emptyState}>No appointments in this view.</div>
                    )}
                </section>
                </>)}

            {rescheduleId && (
                <div className={styles.modalBackdrop}>
                    <div className={styles.modalCard}>
                        <h3>Reschedule appointment</h3>
                        <label>
                            Date
                            <input type="date" value={rescheduleDate} onChange={(event) => setRescheduleDate(event.target.value)} disabled={savingReschedule} />
                        </label>
                        <label>
                            Time
                            <input type="time" value={rescheduleTime} onChange={(event) => setRescheduleTime(event.target.value)} disabled={savingReschedule} />
                        </label>
                        <div className={styles.modalActions}>
                            <button type="button" onClick={() => closeRescheduleModal()} disabled={savingReschedule}>Close</button>
                            <button type="button" onClick={handleRescheduleSubmit} disabled={savingReschedule}>
                                {savingReschedule ? 'Saving…' : 'Save changes'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
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
