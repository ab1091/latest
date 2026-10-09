'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { MessageCircle, Phone, Calendar as CalendarIcon, ListTodo } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { ConversationsInner } from '@/components/panels/ConversationsPanel';
import { CallsPanel } from '@/components/panels/CallsPanel';
import { CalendarPanel } from '@/components/panels/CalendarPanel';
import { AppointmentsPanel } from '@/components/panels/AppointmentsPanel';
import { hasModuleAccess } from '@/lib/permissions';
import styles from './communication.module.css';

type Tab = 'conversations' | 'calls' | 'calendar' | 'appointments';

export default function CommunicationPage() {
    const { user, accessToken, isLoading } = useAuth();
    const router = useRouter();
    const canSeeConversations = user?.role === 'admin' || user?.role === 'super_admin';

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'communication', 'staff')) {
            router.replace('/dashboard');
        }
    }, [isLoading, accessToken, user, router]);

    const tabs = useMemo(() => [
        ...(canSeeConversations ? [{ key: 'conversations' as Tab, label: 'Conversations', icon: MessageCircle }] : []),
        { key: 'calls' as Tab, label: 'Call History', icon: Phone },
        { key: 'calendar' as Tab, label: 'Calendar', icon: CalendarIcon },
        { key: 'appointments' as Tab, label: 'Appointments', icon: ListTodo },
    ], [canSeeConversations]);

    const [tab, setTab] = useState<Tab>(canSeeConversations ? 'conversations' : 'calls');
    const [counts, setCounts] = useState<{
        conversations?: number;
        calls?: number;
        appointments?: number;
    }>({});

    useEffect(() => {
        if (!accessToken) return;
        const fetchCounts = async () => {
            const h = { Authorization: `Bearer ${accessToken}` };
            try {
                const [cRes, clRes, aRes] = await Promise.allSettled([
                    fetch('/api/conversations', { headers: h }).then(r => r.json()),
                    fetch('/api/calls', { headers: h }).then(r => r.json()),
                    fetch('/api/appointments', { headers: h }).then(r => r.json()),
                ]);
                const next: typeof counts = {};
                if (cRes.status === 'fulfilled' && cRes.value?.success) {
                    next.conversations = cRes.value.data?.conversations?.length ?? 0;
                }
                if (clRes.status === 'fulfilled' && clRes.value?.success) {
                    next.calls = clRes.value.data?.calls?.length ?? 0;
                }
                if (aRes.status === 'fulfilled' && aRes.value?.success) {
                    next.appointments = aRes.value.data?.appointments?.length ?? 0;
                }
                setCounts(next);
            } catch {}
        };
        fetchCounts();
        const poll = setInterval(fetchCounts, 15000);
        return () => clearInterval(poll);
    }, [accessToken]);

    return (
        <div className={styles.page}>
            <SideNav />
            <main className={styles.main}>
                <div className={styles.header}>
                    <h1 className={styles.title}>Communication</h1>
                    <p className={styles.subtitle}>Conversations, calls, calendar and appointments, all in one place.</p>
                </div>

                <div className={styles.tabRail}>
                    {tabs.map(({ key, label, icon: Icon }) => {
                        const count = counts[key as keyof typeof counts];
                        return (
                            <button
                                key={key}
                                type="button"
                                className={`${styles.tab} ${tab === key ? styles.tabActive : ''}`}
                                onClick={() => setTab(key)}
                            >
                                <Icon size={14} />
                                <span>{label}</span>
                                {typeof count === 'number' && (
                                    <span className={styles.tabBadge}>{count}</span>
                                )}
                            </button>
                        );
                    })}
                </div>

                <div className={styles.tabBody}>
                    {tab === 'conversations' && canSeeConversations && (
                        <Suspense>
                            <ConversationsInner embedded />
                        </Suspense>
                    )}
                    {tab === 'calls' && (
                        <Suspense>
                            <CallsPanel embedded />
                        </Suspense>
                    )}
                    {tab === 'calendar' && <CalendarPanel embedded />}
                    {tab === 'appointments' && <AppointmentsPanel embedded />}
                </div>
            </main>
        </div>
    );
}
