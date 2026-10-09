'use client';

import { useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { SideNav } from '@/components/SideNav/SideNav';
import { FileText, Download } from 'lucide-react';

const REPORTS = [
    { id: 'calls',        label: 'Call Reports',        desc: 'All call history with outcomes and duration',   endpoint: '/api/calls' },
    { id: 'appointments', label: 'Appointment Reports',  desc: 'Bookings, confirmations, cancellations',        endpoint: '/api/appointments' },
    { id: 'leads',        label: 'Lead Reports',         desc: 'Lead pipeline and conversion stats',            endpoint: '/api/leads' },
    { id: 'conversations',label: 'Conversation Reports', desc: 'AI conversation logs with leads',               endpoint: '/api/conversations' },
];

export default function ReportsPage() {
    const { accessToken, user, isLoading } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'staff', 'super_admin'].includes(user.role)) {
            router.replace('/user/dashboard');
        }
    }, [isLoading, accessToken, user, router]);

    const handleExport = async (report: typeof REPORTS[0]) => {
        if (!accessToken) return;
        try {
            const res = await fetch(report.endpoint, { headers: { Authorization: `Bearer ${accessToken}` } });
            const data = await res.json();
            const items = data?.data?.[report.id] || data?.data || [];
            const csv = [
                Object.keys(items[0] || {}).join(','),
                ...items.map((row: any) => Object.values(row).map(v => `"${v}"`).join(',')),
            ].join('\n');

            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${report.id}_report_${new Date().toISOString().slice(0, 10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
        } catch {
            alert('Export failed. Please try again.');
        }
    };

    return (
        <div style={{ display: 'flex', minHeight: '100vh' }}>
            <SideNav />
            <main style={{ marginLeft: 220, flex: 1, padding: 32 }}>
                <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Reports</h1>
                <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 32 }}>Export business data as CSV</p>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
                    {REPORTS.map(report => (
                        <div key={report.id} style={{
                            background: 'var(--card-bg)', border: '1px solid var(--border)',
                            borderRadius: 12, padding: 20,
                            display: 'flex', flexDirection: 'column', gap: 12,
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <div style={{ background: '#d4a94f20', borderRadius: 8, padding: 8 }}>
                                    <FileText size={18} color="#d4a94f" />
                                </div>
                                <div>
                                    <div style={{ fontWeight: 600, fontSize: 14 }}>{report.label}</div>
                                    <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{report.desc}</div>
                                </div>
                            </div>
                            <button
                                onClick={() => handleExport(report)}
                                style={{
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                                    padding: '8px 16px', background: '#d4a94f', color: '#14100a',
                                    border: 'none', borderRadius: 8, cursor: 'pointer',
                                    fontSize: 13, fontWeight: 600, marginTop: 'auto',
                                }}
                            >
                                <Download size={14} /> Export CSV
                            </button>
                        </div>
                    ))}
                </div>
            </main>
        </div>
    );
}
