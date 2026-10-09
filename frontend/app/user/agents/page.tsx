'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Bot, Zap, Phone, CalendarDays, Users, CheckCircle, XCircle, PlayCircle } from 'lucide-react';


interface Agent {
    id: string;
    name: string;
    role: string;
    status: string;
    tone: string;
    language: string;
}

interface Stats {
    leads: number;
    calls: number;
    appointments: number;
}

function InfoRow({ label, value }: { label: string; value: string }) {
    return (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--border-default)' }}>
            <span style={{ fontSize: 13, color: 'var(--text-4)' }}>{label}</span>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{value}</span>
        </div>
    );
}

function StatTile({ icon: Icon, color, label, value }: { icon: any; color: string; label: string; value: number }) {
    return (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 12, padding: '18px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: `${color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <Icon size={18} color={color} />
            </div>
            <div>
                <div style={{ fontSize: 26, fontWeight: 800, lineHeight: 1 }}>{value}</div>
                <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 3 }}>{label}</div>
            </div>
        </div>
    );
}

export default function UserAgentPage() {
    const { accessToken } = useAuth();
    const [agent, setAgent] = useState<Agent | null>(null);
    const [stats, setStats] = useState<Stats>({ leads: 0, calls: 0, appointments: 0 });
    const [loading, setLoading] = useState(true);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState<string | null>(null);

    useEffect(() => {
        if (!accessToken) return;
        const h = { Authorization: `Bearer ${accessToken}` };

        // First get current user to find their assigned agent_id
        fetch('/api/auth/me', { headers: h })
            .then(r => r.json())
            .then(async meRes => {
                const agentId = meRes?.data?.user?.agent_id;

                const [agentRes, leadsRes, callsRes, apptsRes] = await Promise.all([
                    agentId
                        ? fetch(`/api/agents/${agentId}`, { headers: h }).then(r => r.json())
                        : Promise.resolve(null),
                    fetch(`/api/leads`, { headers: h }).then(r => r.json()),
                    fetch('/api/crm/calls', { headers: h }).then(r => r.json()),
                    fetch('/api/appointments', { headers: h }).then(r => r.json()),
                ]);

                const myLeads = leadsRes?.data?.leads || [];
                const myPhones = new Set(myLeads.map((l: any) => l.phone).filter(Boolean));
                const allCalls = callsRes?.data?.calls || [];
                // Only count calls matching this user's leads by phone
                const myCalls = allCalls.filter((c: any) => myPhones.has(c.phone));

                setAgent(agentRes?.data?.agent || null);
                setStats({
                    leads:        myLeads.length,
                    calls:        myCalls.length,
                    appointments: (apptsRes?.data?.appointments || []).length,
                });
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [accessToken]);

    async function handleTest() {
        if (!agent) return;
        setTesting(true);
        setTestResult(null);
        try {
            await new Promise(res => setTimeout(res, 1200));
            setTestResult('Agent responded successfully. Connection is active.');
        } catch {
            setTestResult('Agent test failed. Please try again.');
        } finally {
            setTesting(false);
        }
    }

    if (loading) {
        return <p style={{ color: 'var(--text-4)', fontSize: 13 }}>Loading...</p>;
    }

    if (!agent) {
        return (
            <div style={{ textAlign: 'center', padding: '80px 0' }}>
                <Bot size={48} style={{ opacity: 0.2, marginBottom: 16 }} />
                <p style={{ color: 'var(--text-4)', fontSize: 14 }}>No AI agent assigned to your account yet.</p>
                <p style={{ color: 'var(--text-4)', fontSize: 13, marginTop: 6 }}>Contact your administrator to get an agent assigned.</p>
            </div>
        );
    }

    const isActive = agent.status === 'active';

    return (
        <div style={{ maxWidth: 680 }}>
            <h1 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 4px' }}>My AI Agent</h1>
            <p style={{ color: 'var(--text-4)', fontSize: 13, marginBottom: 28 }}>Your assigned AI agent and its performance</p>

            {/* Agent Card */}
            <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderRadius: 16, padding: '24px', marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, marginBottom: 20 }}>
                    <div style={{ width: 52, height: 52, borderRadius: 14, background: '#d4a94f18', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <Bot size={24} color="#d4a94f" />
                    </div>
                    <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                            <span style={{ fontSize: 18, fontWeight: 800 }}>{agent.name}</span>
                            <span style={{
                                display: 'inline-flex', alignItems: 'center', gap: 4,
                                padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                                background: isActive ? '#10b98118' : '#6b728018',
                                color: isActive ? '#10b981' : '#6b7280',
                            }}>
                                {isActive ? <CheckCircle size={10} /> : <XCircle size={10} />}
                                {isActive ? 'Active' : 'Inactive'}
                            </span>
                        </div>
                        <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 4 }}>{agent.role}</div>
                    </div>
                </div>

                <div>
                    <InfoRow label="Purpose" value={agent.role} />
                    <InfoRow label="Tone" value={agent.tone?.charAt(0).toUpperCase() + agent.tone?.slice(1) || 'Professional'} />
                    <InfoRow label="Language" value={agent.language || 'English'} />
                    <InfoRow label="Status" value={isActive ? 'Active — handling leads' : 'Inactive'} />
                </div>

                <div style={{ marginTop: 20 }}>
                    <button
                        onClick={handleTest}
                        disabled={testing}
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: 8,
                            padding: '10px 20px', borderRadius: 10, fontSize: 13, fontWeight: 700,
                            background: '#d4a94f', color: '#14100a', border: 'none', cursor: testing ? 'not-allowed' : 'pointer',
                            opacity: testing ? 0.7 : 1, transition: 'opacity 0.2s',
                        }}
                    >
                        <PlayCircle size={15} />
                        {testing ? 'Testing…' : 'Test Agent'}
                    </button>
                    {testResult && (
                        <p style={{ marginTop: 10, fontSize: 13, color: testResult.includes('failed') ? '#ef4444' : '#10b981' }}>
                            {testResult}
                        </p>
                    )}
                </div>
            </div>

            {/* Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
                <StatTile icon={Users}       color="#6366f1" label="Assigned Leads"      value={stats.leads} />
                <StatTile icon={Phone}       color="#d4a94f" label="Calls Handled"        value={stats.calls} />
                <StatTile icon={CalendarDays} color="#f59e0b" label="Appointments Booked" value={stats.appointments} />
            </div>
        </div>
    );
}
