'use client';

import React, { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import styles from './CalendarGrid.module.css';

interface Appointment {
    id: string;
    start_time: string;
    end_time: string;
    service_name?: string;
    provider_name?: string;
    status: string;
}

interface Holiday {
    date: string;
    name: string;
}

interface EmergencyBlock {
    id: string;
    start_time: string;
    end_time: string;
    reason: string;
    ai_explanation: string | null;
    status: string;
}

interface CalendarGridProps {
    appointments: Appointment[];
    holidays?: Holiday[];
    emergencyBlocks?: EmergencyBlock[];
    onDayClick?: (date: Date) => void;
}

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export function CalendarGrid({ appointments, holidays, emergencyBlocks, onDayClick }: CalendarGridProps) {
    const [currentDate, setCurrentDate] = useState(new Date());

    const startOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
    const endOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0);
    const startDay = startOfMonth.getDay();
    const totalDays = endOfMonth.getDate();

    const prevMonth = () => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
    const nextMonth = () => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
    const monthName = currentDate.toLocaleString('default', { month: 'long', year: 'numeric' });

    const getAppointmentsForDay = (day: number) => {
        const dateStr = new Date(currentDate.getFullYear(), currentDate.getMonth(), day).toDateString();
        return appointments.filter(apt => new Date(apt.start_time).toDateString() === dateStr);
    };

    const getEmergencyBlocksForDay = (day: number) => {
        const dateObj = new Date(currentDate.getFullYear(), currentDate.getMonth(), day);
        const dayStart = new Date(dateObj); dayStart.setHours(0, 0, 0, 0);
        const dayEnd   = new Date(dateObj); dayEnd.setHours(23, 59, 59, 999);
        return (emergencyBlocks || []).filter(b =>
            b.status === 'active' &&
            new Date(b.start_time) <= dayEnd &&
            new Date(b.end_time) >= dayStart
        );
    };

    const daysArray = [];

    for (let i = 0; i < startDay; i++) {
        daysArray.push(<div key={`pad-${i}`} className={styles.dayPadding} />);
    }

    for (let d = 1; d <= totalDays; d++) {
        const dayApts = getAppointmentsForDay(d);
        const dateObj = new Date(currentDate.getFullYear(), currentDate.getMonth(), d);
        const isToday = new Date().toDateString() === dateObj.toDateString();
        const holiday = holidays?.find(h => new Date(h.date).toDateString() === dateObj.toDateString());
        const dayBlocks = getEmergencyBlocksForDay(d);
        const isBlocked = dayBlocks.length > 0;

        daysArray.push(
            <div
                key={d}
                className={`${styles.day} ${isToday ? styles.today : ''} ${holiday ? styles.holiday : ''} ${isBlocked ? styles.emergencyDay : ''}`}
                onClick={() => onDayClick?.(dateObj)}
            >
                <div className={styles.dayHeaderRow}>
                    <span className={styles.dayNumber}>{d}</span>
                    {holiday && <span className={styles.holidayLabel} title={holiday.name}>{holiday.name}</span>}
                </div>
                {isBlocked && (
                    <div className={styles.emergencyBanner} title={dayBlocks[0].ai_explanation || dayBlocks[0].reason}>
                        🚨 {dayBlocks[0].reason.length > 16 ? dayBlocks[0].reason.slice(0, 16) + '…' : dayBlocks[0].reason}
                    </div>
                )}
                <div className={styles.aptIndicators}>
                    {dayApts.slice(0, 3).map(apt => {
                        const time = new Date(apt.start_time).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
                        return (
                            <div
                                key={apt.id}
                                className={`${styles.aptItem} ${styles[apt.status] || ''}`}
                                title={`${apt.service_name} with ${apt.provider_name || 'Clinic'}`}
                            >
                                <span className={styles.aptTime}>{time}</span>
                                <span className={styles.aptService}>{apt.service_name}</span>
                            </div>
                        );
                    })}
                    {dayApts.length > 3 && <div className={styles.moreApts}>+{dayApts.length - 3} more</div>}
                </div>
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2>{monthName}</h2>
                <div className={styles.controls}>
                    <button onClick={prevMonth} className={styles.controlBtn}><ChevronLeft size={18} /></button>
                    <button onClick={() => setCurrentDate(new Date())} className={styles.todayBtn}>Today</button>
                    <button onClick={nextMonth} className={styles.controlBtn}><ChevronRight size={18} /></button>
                </div>
            </div>
            <div className={styles.grid}>
                {DAYS.map(day => <div key={day} className={styles.dayHeader}>{day}</div>)}
                {daysArray}
            </div>
        </div>
    );
}
