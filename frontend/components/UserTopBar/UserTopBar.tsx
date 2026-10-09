'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Bell, Plus, Phone, CalendarDays, Users } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

export function UserTopBar() {
    const { user } = useAuth();
    const router = useRouter();
    const [search, setSearch] = useState('');

    const displayName = [user?.firstName, user?.lastName].filter(Boolean).join(' ') || 'User';
    const initials = displayName.split(' ').map((p: string) => p[0]).join('').slice(0, 2).toUpperCase() || 'U';

    return (
        <div style={{
            height: 60, flexShrink: 0,
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '0 28px',
            borderBottom: '1px solid var(--border-default)',
            background: 'var(--bg-card)',
            position: 'sticky', top: 0, zIndex: 30,
        }}>
            {/* Search */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: 'var(--bg-elevated)', border: '1px solid var(--border-default)',
                borderRadius: 10, padding: '0 12px', flex: 1, maxWidth: 360,
            }}>
                <Search size={14} color="var(--text-4)" />
                <input
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    placeholder="Search leads, conversations, calls..."
                    style={{
                        background: 'none', border: 'none', outline: 'none',
                        fontSize: 13, color: 'var(--text-1)', flex: 1, height: 36,
                        fontFamily: 'var(--font-inter)',
                    }}
                />
                <span style={{ fontSize: 11, color: 'var(--text-4)', background: 'var(--bg-card)', padding: '2px 6px', borderRadius: 5, border: '1px solid var(--border-subtle)' }}>⌘K</span>
            </div>

            <div style={{ flex: 1 }} />

            {/* Action Buttons */}
            <button
                onClick={() => router.push('/user/calls')}
                style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '7px 14px', borderRadius: 9, fontSize: 12, fontWeight: 700,
                    background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.25)',
                    color: '#f59e0b', cursor: 'pointer',
                }}
            >
                <Plus size={13} /> New Call
            </button>

            <button
                onClick={() => router.push('/user/appointments')}
                style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '7px 14px', borderRadius: 9, fontSize: 12, fontWeight: 700,
                    background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)',
                    color: '#a5b4fc', cursor: 'pointer',
                }}
            >
                <CalendarDays size={13} /> New Appointment
            </button>

            <button
                onClick={() => router.push('/user/leads')}
                style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '7px 14px', borderRadius: 9, fontSize: 12, fontWeight: 700,
                    background: 'linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%)',
                    border: 'none', color: '#fff', cursor: 'pointer',
                    boxShadow: '0 3px 10px rgba(185, 134, 42,0.3)',
                }}
            >
                <Plus size={13} /> New Lead
            </button>

            {/* Bell */}
            <button style={{
                width: 36, height: 36, borderRadius: 10,
                background: 'var(--bg-elevated)', border: '1px solid var(--border-default)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', position: 'relative',
            }}>
                <Bell size={15} color="var(--text-4)" />
            </button>

            {/* User Avatar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                    width: 34, height: 34, borderRadius: 10,
                    background: 'rgba(212, 169, 79,0.15)', border: '1px solid rgba(212, 169, 79,0.25)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 12, fontWeight: 800, color: '#d4a94f',
                }}>{initials}</div>
                <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)', lineHeight: 1.2 }}>{displayName}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-4)' }}>Sales Agent</div>
                </div>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#10b981', marginLeft: 2 }} />
            </div>
        </div>
    );
}
