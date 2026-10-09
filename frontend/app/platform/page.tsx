'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Building2, Users, TrendingUp, Phone, MessageSquare, Workflow, LogIn } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useAgencyScope } from '@/contexts/AgencyScopeContext';
import { SideNav } from '@/components/SideNav/SideNav';
import styles from './platform.module.css';

interface Agency {
    id: string; name: string; email: string; status: string; created_at: string;
    staff_count: number; lead_count: number; active_workflows: number; plan_name: string;
}
interface Analytics {
    total_agencies: number; total_leads: number; total_calls: number;
    total_messages: number; active_workflows: number; mrr_cents: number;
}

export default function PlatformPage() {
    const { accessToken, isLoading, user } = useAuth();
    const { setAgency } = useAgencyScope();
    const router = useRouter();
    const [agencies, setAgencies] = useState<Agency[]>([]);
    const [analytics, setAnalytics] = useState<Analytics | null>(null);

    const manageAgency = (a: Agency) => {
        setAgency({ id: a.id, name: a.name });
        router.push('/dashboard');
    };

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && user.role !== 'super_admin') router.replace('/dashboard');
    }, [isLoading, accessToken, user, router]);

    const load = useCallback(async () => {
        if (!accessToken) return;
        const headers = { Authorization: `Bearer ${accessToken}` };
        const [agenciesRes, analyticsRes] = await Promise.all([
            fetch('/api/platform/agencies', { headers }).then(r => r.json()),
            fetch('/api/platform/analytics', { headers }).then(r => r.json()),
        ]);
        if (agenciesRes.success) setAgencies(agenciesRes.data.agencies);
        if (analyticsRes.success) setAnalytics(analyticsRes.data);
    }, [accessToken]);

    useEffect(() => { load(); }, [load]);

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>
                <div className={styles.header}>
                    <div className={styles.headerIcon}><Building2 size={22} /></div>
                    <div className={styles.headerInfo}>
                        <h1>Platform</h1>
                        <p>Cross-agency view — every business running on AllZone.</p>
                    </div>
                </div>

                {analytics && (
                    <div className={styles.statGrid}>
                        <StatCard icon={<Building2 size={16} />} label="Agencies" value={analytics.total_agencies} />
                        <StatCard icon={<Users size={16} />} label="Total Leads" value={analytics.total_leads} />
                        <StatCard icon={<Phone size={16} />} label="Total Calls" value={analytics.total_calls} />
                        <StatCard icon={<MessageSquare size={16} />} label="Total Messages" value={analytics.total_messages} />
                        <StatCard icon={<Workflow size={16} />} label="Active Workflows" value={analytics.active_workflows} />
                        <StatCard icon={<TrendingUp size={16} />} label="MRR" value={`$${(analytics.mrr_cents / 100).toFixed(0)}`} />
                    </div>
                )}

                <div className={styles.tableWrap}>
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                <th>Agency</th><th>Plan</th><th>Staff</th><th>Leads</th><th>Active Workflows</th><th>Status</th><th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {agencies.map(a => (
                                <tr key={a.id}>
                                    <td>
                                        <div style={{ fontWeight: 700 }}>{a.name}</div>
                                        <div style={{ fontSize: 11, color: 'var(--text-4)' }}>{a.email}</div>
                                    </td>
                                    <td>{a.plan_name}</td>
                                    <td>{a.staff_count}</td>
                                    <td>{a.lead_count}</td>
                                    <td>{a.active_workflows}</td>
                                    <td><span className={styles.statusPill}>{a.status}</span></td>
                                    <td>
                                        <button
                                            onClick={() => manageAgency(a)}
                                            style={{
                                                display: 'flex', alignItems: 'center', gap: 5,
                                                padding: '6px 12px', borderRadius: 7, border: 'none',
                                                background: 'var(--primary)', color: 'var(--on-primary)',
                                                fontSize: 12, fontWeight: 600, cursor: 'pointer',
                                            }}
                                        >
                                            <LogIn size={13} /> Manage
                                        </button>
                                    </td>
                                </tr>
                            ))}
                            {agencies.length === 0 && (
                                <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-4)', padding: 30 }}>No agencies yet.</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
    return (
        <div className={styles.statCard}>
            <div style={{ color: '#818cf8' }}>{icon}</div>
            <div className={styles.statValue}>{value}</div>
            <div className={styles.statLabel}>{label}</div>
        </div>
    );
}
