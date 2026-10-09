'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { ChevronLeft, ChevronRight, CalendarDays, ArrowLeft, Clock } from 'lucide-react';
import styles from '@/app/calendar/calendar.module.css';

interface Appointment {
    id: string;
    start_time: string;
    end_time: string;
    status: string;
    notes: string | null;
    service_name: string | null;
    provider_name: string | null;
    first_name: string | null;
    last_name: string | null;
}

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

function getDotStyle(status: string) {
    const s = status.toLowerCase();
    if (s === 'confirmed' || s === 'completed') return styles.dotConfirmed;
    if (s === 'cancelled' || s === 'no_show') return styles.dotCancelled;
    if (s === 'pending') return styles.dotNoAnswer;
    return styles.dotDefault;
}

function getBadgeStyle(status: string) {
    const s = status.toLowerCase();
    if (s === 'confirmed' || s === 'completed') return styles.badgeConfirmed;
    if (s === 'cancelled' || s === 'no_show') return styles.badgeCancelled;
    if (s === 'pending') return styles.badgeNoAnswer;
    return styles.badgeDefault;
}

export function CalendarPanel({ embedded = false }: { embedded?: boolean } = {}) {
    const { accessToken } = useAuth();
    const router = useRouter();
    const [appointments, setAppointments] = useState<Appointment[]>([]);
    const [loading, setLoading] = useState(true);
    const [today] = useState(new Date());
    const [viewDate, setViewDate] = useState(new Date());
    const [selectedDay, setSelectedDay] = useState<number | null>(null);

    useEffect(() => {
        if (!accessToken) return;
        fetch('/api/appointments', {
            headers: { Authorization: `Bearer ${accessToken}` },
        })
            .then((r) => r.json())
            .then((d) => setAppointments(d.data?.appointments || []))
            .finally(() => setLoading(false));
    }, [accessToken]);

    const year = viewDate.getFullYear();
    const month = viewDate.getMonth();

    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const apptsByDay: Record<number, Appointment[]> = {};
    appointments.forEach((a) => {
        const d = new Date(a.start_time);
        if (d.getFullYear() === year && d.getMonth() === month) {
            const day = d.getDate();
            if (!apptsByDay[day]) apptsByDay[day] = [];
            apptsByDay[day].push(a);
        }
    });

    const prevMonth = () => setViewDate(new Date(year, month - 1, 1));
    const nextMonth = () => setViewDate(new Date(year, month + 1, 1));

    const selectedAppts = selectedDay ? (apptsByDay[selectedDay] || []) : [];

    const cells: (number | null)[] = [
        ...Array(firstDay).fill(null),
        ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
    ];

    return (
        <div className={embedded ? undefined : styles.page}>
            {!embedded && (
                <div className={styles.header}>
                    <button className={styles.backBtn} onClick={() => router.back()}>
                        <ArrowLeft size={18} />
                    </button>
                    <CalendarDays size={20} />
                    <h1 className={styles.title}>Appointment Calendar</h1>
                    <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text-muted, #94a3b8)', background: 'var(--bg-elevated, rgba(255,255,255,0.04))', padding: '4px 10px', borderRadius: 6, border: '1px solid var(--border-default, rgba(255,255,255,0.08))' }}>
                        <span style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: '#22c55e', display: 'inline-block' }} />
                        <span>Google Calendar: <strong style={{ color: 'var(--text-primary, #f8fafc)' }}>shieldsquadagency@gmail.com</strong></span>
                    </div>
                </div>
            )}

            <div className={styles.layout}>
                <div className={styles.calendarBox}>
                    <div className={styles.navRow}>
                        <button className={styles.navBtn} onClick={prevMonth}><ChevronLeft size={16} /></button>
                        <span className={styles.monthLabel}>{MONTHS[month]} {year}</span>
                        <button className={styles.navBtn} onClick={nextMonth}><ChevronRight size={16} /></button>
                    </div>

                    <div className={styles.dayHeaders}>
                        {DAYS.map((d) => <div key={d} className={styles.dayHeader}>{d}</div>)}
                    </div>

                    <div className={styles.grid}>
                        {cells.map((day, i) => {
                            if (!day) return <div key={`empty-${i}`} className={styles.emptyCell} />;
                            const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
                            const hasAppts = !!apptsByDay[day];
                            const isSelected = selectedDay === day;
                            return (
                                <div
                                    key={day}
                                    className={`${styles.cell} ${isToday ? styles.today : ''} ${isSelected ? styles.selected : ''} ${hasAppts ? styles.hasAppt : ''}`}
                                    onClick={() => setSelectedDay(isSelected ? null : day)}
                                >
                                    <span className={styles.dayNum}>{day}</span>
                                    {hasAppts && (
                                        <div className={styles.dots}>
                                            {apptsByDay[day].slice(0, 3).map((a) => (
                                                <span key={a.id} className={`${styles.dot} ${getDotStyle(a.status)}`} />
                                            ))}
                                            {apptsByDay[day].length > 3 && (
                                                <span className={styles.moreCount}>+{apptsByDay[day].length - 3}</span>
                                            )}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    <div className={styles.legend}>
                        <span className={`${styles.dot} ${styles.dotConfirmed}`} /> Confirmed / Completed
                        <span className={`${styles.dot} ${styles.dotNoAnswer}`} /> Pending
                        <span className={`${styles.dot} ${styles.dotCancelled}`} /> Cancelled / No-show
                        <span className={`${styles.dot} ${styles.dotDefault}`} /> Other
                    </div>
                </div>

                <div className={styles.sidebar}>
                    <div className={styles.sidebarTitle}>
                        {selectedDay
                            ? `${MONTHS[month]} ${selectedDay}, ${year}`
                            : 'Select a day'}
                    </div>

                    {loading && <p className={styles.empty}>Loading…</p>}

                    {!loading && !selectedDay && (
                        <p className={styles.empty}>Click a day to see appointments</p>
                    )}

                    {!loading && selectedDay && selectedAppts.length === 0 && (
                        <p className={styles.empty}>No appointments this day</p>
                    )}

                    {selectedAppts.map((a) => {
                        const start = new Date(a.start_time);
                        const end = new Date(a.end_time);
                        const time = `${start.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })} – ${end.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;
                        return (
                            <div key={a.id} className={styles.apptCard}>
                                <div className={styles.apptTime}>
                                    <Clock size={11} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                                    {time}
                                </div>
                                <div className={styles.apptService}>{[a.first_name, a.last_name].filter(Boolean).join(' ') || 'Appointment'}</div>
                                {a.service_name && <div className={styles.apptMeta}>{a.service_name}</div>}
                                {a.provider_name && <div className={styles.apptMeta}>with {a.provider_name}</div>}
                                {a.notes && <div className={styles.apptMeta}>{a.notes}</div>}
                                <span className={`${styles.badge} ${getBadgeStyle(a.status)}`}>
                                    {a.status || 'Unknown'}
                                </span>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
