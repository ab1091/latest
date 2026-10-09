'use client';

import { useEffect, useRef, useState } from 'react';
import { Filter, ChevronDown, X } from 'lucide-react';

export interface BehaviorFilterValue {
    scoreBand: string;   // '' | 'hot' | 'warm' | 'cold' | 'new'
    engagement: string;  // '' | 'replied' | 'no_reply'
    followUp: string;    // '' | '1'
    appointment: string; // '' | 'upcoming' | 'no_show' | 'completed' | 'none'
    optedOut: string;    // '' | 'true' | 'false'
}

export const DEFAULT_BEHAVIOR_FILTERS: BehaviorFilterValue = {
    scoreBand: '', engagement: '', followUp: '', appointment: '', optedOut: '',
};

export function activeBehaviorFilterCount(v: BehaviorFilterValue): number {
    return Object.values(v).filter(Boolean).length;
}

const SECTIONS: {
    key: keyof BehaviorFilterValue;
    label: string;
    options: { value: string; label: string; color?: string }[];
}[] = [
    {
        key: 'scoreBand', label: 'Lead Temperature',
        options: [
            { value: 'hot', label: '🔥 Hot', color: '#f87171' },
            { value: 'warm', label: 'Warm', color: '#fbbf24' },
            { value: 'cold', label: 'Cold', color: '#7fded0' },
            { value: 'new', label: 'New', color: '#89a7a1' },
        ],
    },
    {
        key: 'engagement', label: 'Engagement',
        options: [
            { value: 'replied', label: 'Has replied' },
            { value: 'no_reply', label: 'Never replied' },
        ],
    },
    {
        key: 'followUp', label: 'Follow-up',
        options: [
            { value: '1', label: 'Needs follow-up (open task)' },
        ],
    },
    {
        key: 'appointment', label: 'Appointments',
        options: [
            { value: 'upcoming', label: 'Upcoming booked' },
            { value: 'no_show', label: 'Missed (no-show)' },
            { value: 'completed', label: 'Completed' },
            { value: 'none', label: 'None booked' },
        ],
    },
    {
        key: 'optedOut', label: 'Contact Status',
        options: [
            { value: 'false', label: 'Active / contactable' },
            { value: 'true', label: 'Opted out (DNC)' },
        ],
    },
];

export function BehaviorFilters({ value, onChange }: { value: BehaviorFilterValue; onChange: (v: BehaviorFilterValue) => void }) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    const count = activeBehaviorFilterCount(value);

    useEffect(() => {
        if (!open) return;
        const onClick = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', onClick);
        return () => document.removeEventListener('mousedown', onClick);
    }, [open]);

    const toggle = (key: keyof BehaviorFilterValue, val: string) => {
        onChange({ ...value, [key]: value[key] === val ? '' : val });
    };

    return (
        <div ref={ref} style={{ position: 'relative' }}>
            <button
                onClick={() => setOpen(o => !o)}
                style={{
                    display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
                    padding: '0.6rem 0.9rem', borderRadius: 10, cursor: 'pointer',
                    background: count > 0 ? 'var(--primary)' : 'var(--bg-card)',
                    border: `1px solid ${count > 0 ? 'var(--primary)' : 'var(--border-default)'}`,
                    color: count > 0 ? '#fff' : 'var(--text-2)', fontSize: '0.85rem', fontWeight: 600,
                }}
            >
                <Filter size={14} /> Filters
                {count > 0 && (
                    <span style={{
                        background: 'rgba(255,255,255,0.25)', borderRadius: 999, fontSize: 11,
                        padding: '1px 7px', fontWeight: 700,
                    }}>{count}</span>
                )}
                <ChevronDown size={13} style={{ opacity: 0.7 }} />
            </button>

            {open && (
                <div style={{
                    position: 'absolute', top: 'calc(100% + 8px)', left: 0, zIndex: 50,
                    width: 320, background: 'var(--bg-card)', border: '1px solid var(--border-default)',
                    borderRadius: 14, boxShadow: '0 12px 40px rgba(0,0,0,0.25)', padding: '14px',
                    display: 'flex', flexDirection: 'column', gap: 14,
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>Behavior Filters</span>
                        {count > 0 && (
                            <button
                                onClick={() => onChange(DEFAULT_BEHAVIOR_FILTERS)}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none',
                                    color: 'var(--text-4)', fontSize: 12, cursor: 'pointer', fontWeight: 600,
                                }}
                            >
                                <X size={12} /> Clear all
                            </button>
                        )}
                    </div>

                    {SECTIONS.map(section => (
                        <div key={section.key}>
                            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 6 }}>
                                {section.label}
                            </div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                {section.options.map(opt => {
                                    const active = value[section.key] === opt.value;
                                    return (
                                        <button
                                            key={opt.value}
                                            onClick={() => toggle(section.key, opt.value)}
                                            style={{
                                                padding: '5px 11px', borderRadius: 20, cursor: 'pointer',
                                                fontSize: 12.5, fontWeight: active ? 700 : 500,
                                                border: `1px solid ${active ? (opt.color || 'var(--primary)') : 'var(--border-default)'}`,
                                                background: active ? `${opt.color || 'var(--primary)'}22` : 'transparent',
                                                color: active ? (opt.color || 'var(--primary)') : 'var(--text-3)',
                                                display: 'flex', alignItems: 'center', gap: 5,
                                            }}
                                        >
                                            {opt.color && (
                                                <span style={{ width: 7, height: 7, borderRadius: '50%', background: opt.color, display: 'inline-block' }} />
                                            )}
                                            {opt.label}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
