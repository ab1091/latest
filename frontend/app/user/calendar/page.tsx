'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { parseApiDate } from '@/lib/date';

interface Appointment {
    id: string; start_time: string; end_time: string;
    status: string; service_name?: string; provider_name?: string; notes?: string;
}

const DAYS   = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

const STATUS_DOT: Record<string, string> = { confirmed: '#10b981', cancelled: '#ef4444' };

export default function UserCalendar() {
    const { accessToken } = useAuth();
    const [appointments, setAppointments] = useState<Appointment[]>([]);
    const [loading,      setLoading]      = useState(true);
    const [today]   = useState(new Date());
    const [viewDate, setViewDate]   = useState(new Date());
    const [selectedDay, setSelectedDay] = useState<number | null>(null);

    useEffect(() => {
        if (!accessToken) return;
        fetch('/api/appointments?includeCancelled=false', { headers: { Authorization: `Bearer ${accessToken}` } })
            .then(r => r.json())
            .then(d => setAppointments(d.data?.appointments || []))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [accessToken]);

    const year  = viewDate.getFullYear();
    const month = viewDate.getMonth();
    const firstDay   = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const apptsByDay: Record<number, Appointment[]> = {};
    appointments.forEach(a => {
        const d = parseApiDate(a.start_time);
        if (d.getFullYear() === year && d.getMonth() === month) {
            const day = d.getDate();
            if (!apptsByDay[day]) apptsByDay[day] = [];
            apptsByDay[day].push(a);
        }
    });

    const cells: (number | null)[] = [
        ...Array(firstDay).fill(null),
        ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
    ];

    const selectedAppts = selectedDay ? (apptsByDay[selectedDay] || []) : [];

    return (
        <div style={{ maxWidth: 900 }}>
            <h1 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 24px' }}>Calendar</h1>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 20 }}>
                {/* Calendar grid */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, overflow: 'hidden' }}>
                    {/* Month nav */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid var(--border-default)' }}>
                        <button onClick={() => setViewDate(new Date(year, month - 1, 1))} style={{ background: 'none', border: '1px solid var(--border-default)', borderRadius: 8, padding: '4px 8px', cursor: 'pointer', color: 'var(--text-2)' }}>
                            <ChevronLeft size={16} />
                        </button>
                        <span style={{ fontWeight: 700, fontSize: 15 }}>{MONTHS[month]} {year}</span>
                        <button onClick={() => setViewDate(new Date(year, month + 1, 1))} style={{ background: 'none', border: '1px solid var(--border-default)', borderRadius: 8, padding: '4px 8px', cursor: 'pointer', color: 'var(--text-2)' }}>
                            <ChevronRight size={16} />
                        </button>
                    </div>

                    {/* Day headers */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', padding: '8px 12px 4px' }}>
                        {DAYS.map(d => (
                            <div key={d} style={{ textAlign: 'center', fontSize: 11, fontWeight: 700, color: 'var(--text-4)', padding: '4px 0' }}>{d}</div>
                        ))}
                    </div>

                    {/* Grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', padding: '0 12px 12px', gap: 4 }}>
                        {cells.map((day, i) => {
                            if (!day) return <div key={`e-${i}`} />;
                            const isToday    = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
                            const isSelected = selectedDay === day;
                            const hasAppts   = !!apptsByDay[day];
                            return (
                                <div key={day} onClick={() => setSelectedDay(isSelected ? null : day)}
                                    style={{
                                        borderRadius: 8, padding: '6px 4px', textAlign: 'center',
                                        cursor: 'pointer', position: 'relative',
                                        background: isSelected ? 'var(--primary)' : isToday ? 'rgba(185, 134, 42,0.1)' : 'transparent',
                                        border: isToday && !isSelected ? '1px solid var(--primary)' : '1px solid transparent',
                                        fontWeight: isToday || isSelected ? 700 : 400,
                                        color: isSelected ? '#fff' : 'var(--text-1)',
                                    }}>
                                    <div style={{ fontSize: 13 }}>{day}</div>
                                    {hasAppts && (
                                        <div style={{ display: 'flex', justifyContent: 'center', gap: 2, marginTop: 2 }}>
                                            {apptsByDay[day].slice(0, 3).map(a => (
                                                <div key={a.id} style={{ width: 4, height: 4, borderRadius: '50%', background: isSelected ? '#fff' : (STATUS_DOT[a.status] || '#6b7280') }} />
                                            ))}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Sidebar */}
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 14, padding: '16px', overflow: 'auto' }}>
                    <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 14, color: 'var(--text-1)' }}>
                        {selectedDay ? `${MONTHS[month]} ${selectedDay}, ${year}` : 'Select a day'}
                    </div>
                    {loading && <p style={{ color: 'var(--text-4)', fontSize: 13 }}>Loading…</p>}
                    {!loading && !selectedDay && <p style={{ color: 'var(--text-4)', fontSize: 13 }}>Click a day to see appointments</p>}
                    {!loading && selectedDay && selectedAppts.length === 0 && <p style={{ color: 'var(--text-4)', fontSize: 13 }}>No appointments this day</p>}
                    {selectedAppts.map(a => {
                        const start = parseApiDate(a.start_time).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                        const end   = parseApiDate(a.end_time).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
                        return (
                            <div key={a.id} style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 10, padding: '12px', marginBottom: 10 }}>
                                <div style={{ fontSize: 12, color: 'var(--text-4)', marginBottom: 4 }}>{start} – {end}</div>
                                <div style={{ fontWeight: 600, fontSize: 14 }}>{a.service_name || 'Appointment'}</div>
                                {a.provider_name && <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 2 }}>With {a.provider_name}</div>}
                                {a.notes && <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 4 }}>{a.notes}</div>}
                                <span style={{
                                    display: 'inline-block', marginTop: 8, padding: '2px 8px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                                    background: `${STATUS_DOT[a.status] || '#6b7280'}20`,
                                    color: STATUS_DOT[a.status] || '#6b7280',
                                }}>{a.status}</span>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
