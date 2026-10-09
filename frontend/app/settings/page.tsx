'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { SideNav } from '@/components/SideNav/SideNav';
import { Settings as SettingsIcon } from 'lucide-react';
import { hasModuleAccess } from '@/lib/permissions';
import styles from './settings.module.css';

type Tab = 'profile' | 'integrations' | 'billing';

export default function SettingsPage() {
    const router = useRouter();
    const [tab, setTab] = useState<Tab>('profile');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [integrations, setIntegrations] = useState([
        { id: 'google',  name: 'Google Calendar',  desc: 'Sync confirmed appointments to Google Calendar', connected: false },
        { id: 'outlook', name: 'Outlook Calendar', desc: 'Sync appointments to Microsoft Outlook Calendar', connected: false },
        { id: 'hubspot', name: 'HubSpot CRM',      desc: 'Bidirectional contact and meeting sync', connected: false },
        { id: 'vapi',    name: 'Vapi Voice AI',    desc: 'AI voice calls via Vapi + Twilio', connected: false },
        { id: 'twilio',  name: 'Twilio SMS',       desc: 'SMS reminders and confirmations', connected: false }
    ]);

    const integrationIcons: Record<string, React.ReactNode> = {
        google: (
            <svg width="28" height="28" viewBox="0 0 48 48" fill="none">
                <path d="M44.5 20H24v8.5h11.8C34.7 33.9 29.8 37 24 37c-7.2 0-13-5.8-13-13s5.8-13 13-13c3.1 0 5.9 1.1 8.1 2.9l6.4-6.4C34.6 5.1 29.6 3 24 3 12.4 3 3 12.4 3 24s9.4 21 21 21c10.5 0 20-7.7 20-21 0-1.3-.2-2.7-.5-4z" fill="#FFC107"/>
                <path d="M6.3 14.7l7 5.1C15.1 16.1 19.2 13 24 13c3.1 0 5.9 1.1 8.1 2.9l6.4-6.4C34.6 5.1 29.6 3 24 3c-7.6 0-14.2 4.3-17.7 10.7z" fill="#FF3D00"/>
                <path d="M24 45c5.5 0 10.5-1.9 14.4-5.1l-6.7-5.5C29.8 36.1 27 37 24 37c-5.8 0-10.7-3.9-12.4-9.3l-7 5.4C8.2 40.8 15.5 45 24 45z" fill="#4CAF50"/>
                <path d="M44.5 20H24v8.5h11.8c-0.8 2.6-2.5 4.8-4.8 6.4l6.7 5.5C41.8 37 45 31 45 24c0-1.3-.2-2.7-.5-4z" fill="#1976D2"/>
            </svg>
        ),
        outlook: (
            <svg width="28" height="28" viewBox="0 0 48 48" fill="none">
                <rect width="48" height="48" rx="8" fill="#0078D4"/>
                <path d="M14 14h20v4H14zM14 20h8v4h-8zM14 26h8v4h-8zM14 32h8v4h-8zM24 20h10v16H24z" fill="white" opacity="0.9"/>
                <rect x="24" y="20" width="10" height="16" rx="1" fill="white" opacity="0.15"/>
                <path d="M10 16h16v16H10z" fill="#004E8C" rx="2"/>
                <ellipse cx="18" cy="24" rx="5" ry="6" fill="white"/>
                <ellipse cx="18" cy="24" rx="3" ry="4" fill="#004E8C"/>
            </svg>
        ),
        hubspot: (
            <svg width="28" height="28" viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="24" r="22" fill="#FF7A59"/>
                <path d="M20 16v8.5c-1.2-.7-2-2-2-3.5 0-2.2 1.8-4 4-4s4 1.8 4 4c0 1.5-.8 2.8-2 3.5V32c0 1.1.9 2 2 2s2-.9 2-2v-4.2c2.4-1.1 4-3.5 4-6.3C32 17.9 28.4 14 24 14c-4.4 0-8 3.9-8 8.5 0 2.8 1.6 5.2 4 6.3V32" stroke="white" strokeWidth="2" fill="none"/>
                <circle cx="24" cy="32" r="2.5" fill="white"/>
            </svg>
        ),
        vapi: (
            <svg width="28" height="28" viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="24" r="22" fill="#6366F1"/>
                <path d="M16 18c0-1.1.9-2 2-2h12c1.1 0 2 .9 2 2v8c0 1.1-.9 2-2 2h-4l-4 4v-4h-4c-1.1 0-2-.9-2-2v-8z" fill="white"/>
                <circle cx="20" cy="22" r="1.5" fill="#6366F1"/>
                <circle cx="24" cy="22" r="1.5" fill="#6366F1"/>
                <circle cx="28" cy="22" r="1.5" fill="#6366F1"/>
            </svg>
        ),
        twilio: (
            <svg width="28" height="28" viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="24" r="22" fill="#F22F46"/>
                <circle cx="24" cy="24" r="8" fill="none" stroke="white" strokeWidth="3"/>
                <circle cx="20" cy="20" r="2.5" fill="white"/>
                <circle cx="28" cy="20" r="2.5" fill="white"/>
                <circle cx="20" cy="28" r="2.5" fill="white"/>
                <circle cx="28" cy="28" r="2.5" fill="white"/>
            </svg>
        ),
    };
    const [showVapiModal, setShowVapiModal] = useState(false);
    const [showTwilioModal, setShowTwilioModal] = useState(false);
    const [vapiData, setVapiData] = useState({ apiKey: '', assistantId: '' });
    const [twilioData, setTwilioData] = useState({ sid: '', authToken: '', phoneNumber: '' });
    const [connectingId, setConnectingId] = useState<string | null>(null);

    const { user, accessToken, isAuthenticated, isLoading: authLoading, isLoggingOut, googleLogin, refreshUser } = useAuth();

    const [profileForm, setProfileForm] = useState({ firstName: '', lastName: '', email: '', phone: '' });
    const [savingProfile, setSavingProfile] = useState(false);
    const [profileMessage, setProfileMessage] = useState('');

    useEffect(() => {
        if (user) {
            setProfileForm({
                firstName: user.firstName || '',
                lastName: user.lastName || '',
                email: user.email || '',
                phone: user.phone || '',
            });
        }
    }, [user]);

    const handleSaveProfile = async () => {
        setSavingProfile(true);
        setProfileMessage('');
        try {
            const res = await fetch('/api/auth/profile', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
                body: JSON.stringify(profileForm),
            });
            if (res.ok) {
                setProfileMessage('Profile updated successfully.');
                await refreshUser();
            } else {
                const data = await res.json().catch(() => ({}));
                setProfileMessage(data.detail || 'Failed to update profile.');
            }
        } catch {
            setProfileMessage('Error saving profile.');
        } finally {
            setSavingProfile(false);
        }
    };

    const triggerGoogleLogin = () => {
        const params = new URLSearchParams({
            client_id: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || '',
            redirect_uri: `${process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000'}/auth/callback`,
            response_type: 'code',
            scope: 'openid email profile https://www.googleapis.com/auth/calendar.events',
            access_type: 'offline',
            prompt: 'consent',
            state: 'calendar_connect',
        });
        window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
    };

    const fetchStatus = useCallback(async () => {
        if (!accessToken || !user) return;
        try {
            const res = await fetch('/api/integrations/status', {
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                    'x-user-id': String(user.id),
                    'x-business-id': String(user.businessId || user.business_id || '')
                }
            });
            const data = await res.json();
            if (data.success) {
                setIntegrations(prev => prev.map(i => ({
                    ...i,
                    connected: data.data[i.id]?.connected || false
                })));
            }
        } catch (err) {
            console.error('Failed to fetch integration status:', err);
        }
    }, [accessToken, user]);

    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    // Handle OAuth callbacks (outlook=success, hubspot=success, etc.)
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        if (params.get('outlook') === 'success') {
            setTab('integrations');
            fetchStatus();
            window.history.replaceState({}, '', '/settings?tab=integrations');
        }
        if (params.get('tab')) {
            const requested = params.get('tab') as Tab;
            const allowed = requested === 'integrations' ? hasModuleAccess(user, 'integrations', 'admin')
                : requested === 'billing' ? hasModuleAccess(user, 'billing', 'admin')
                : true;
            setTab(allowed ? requested : 'profile');
        }
    }, [fetchStatus, user]);

    const handleToggleIntegration = async (id: string) => {
        const item = integrations.find(i => i.id === id);
        if (!item) return;

        if (!item.connected) {
            if (id === 'google') {
                setIntegrations(prev => prev.map(i => i.id === 'google' ? { ...i, connected: true } : i));
            } else if (id === 'outlook') {
                window.location.href = `/api/integrations/outlook/connect?token=${accessToken}`;
            } else if (id === 'hubspot') {
                window.location.href = `/api/integrations/hubspot/authorize?businessId=${user?.businessId}`;
            } else if (id === 'vapi') {
                setShowVapiModal(true);
            } else if (id === 'twilio') {
                setShowTwilioModal(true);
            }
        } else {
            // In a real app, you might want a confirmation modal or an API call to disconnect
            setIntegrations(prev => prev.map(i => i.id === id ? { ...i, connected: false } : i));
        }
    };

    const handleSaveVapi = async () => {
        if (!user || !accessToken) return;
        setIsSubmitting(true);
        try {
            const res = await fetch('/api/integrations/vapi', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                },
                body: JSON.stringify({ businessId: user.businessId, ...vapiData })
            });
            if (res.ok) {
                setShowVapiModal(false);
                fetchStatus();
            }
        } catch (err) {
            console.error('Vapi save error:', err);
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleSaveTwilio = async () => {
        if (!user || !accessToken) return;
        setIsSubmitting(true);
        try {
            const res = await fetch('/api/integrations/twilio', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                },
                body: JSON.stringify({ businessId: user.businessId, ...twilioData })
            });
            if (res.ok) {
                setShowTwilioModal(false);
                fetchStatus();
            }
        } catch (err) {
            console.error('Twilio save error:', err);
        } finally {
            setIsSubmitting(false);
        }
    };

    const confirmGoogleConnect = async () => {
        // This is handled by handleGoogleConnect now
    };

    useEffect(() => {
        if (!authLoading) {
            if (!isAuthenticated && !isLoggingOut) {
                router.push('/login');
            }
        }
    }, [authLoading, isAuthenticated, isLoggingOut, router]);

    if (authLoading) return null;

    const tabs: [Tab, string][] = [
        ['profile', 'Profile'],
        ...(hasModuleAccess(user, 'integrations', 'admin') ? [['integrations', 'Integrations'] as [Tab, string]] : []),
        ...(hasModuleAccess(user, 'billing', 'admin') ? [['billing', 'Billing'] as [Tab, string]] : []),
    ];

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>
                <div className={styles.header}>
                    <div className={styles.headerIcon}><SettingsIcon size={22} color="var(--primary-text)" /></div>
                    <div>
                        <h1>Settings</h1>
                        <p>Manage your account and integrations</p>
                    </div>
                </div>

                <div className={styles.grid}>
                    {/* Sidebar Tabs */}
                    <div className={styles.tabsNav}>
                        {tabs.map(([v, l]) => (
                            <button
                                key={v}
                                onClick={() => setTab(v)}
                                className={`${styles.tabBtn} ${tab === v ? styles.tabActive : ''}`}
                            >
                                {l}
                            </button>
                        ))}
                    </div>

                    {/* Content Area */}
                    <div className={styles.content}>
                        {tab === 'profile' && (
                            <div className={styles.profileSection}>
                                <div className={styles.row}>
                                    <div className={styles.field}>
                                        <label>First name</label>
                                        <input
                                            value={profileForm.firstName}
                                            onChange={e => setProfileForm(f => ({ ...f, firstName: e.target.value }))}
                                            className={styles.input}
                                        />
                                    </div>
                                    <div className={styles.field}>
                                        <label>Last name</label>
                                        <input
                                            value={profileForm.lastName}
                                            onChange={e => setProfileForm(f => ({ ...f, lastName: e.target.value }))}
                                            className={styles.input}
                                        />
                                    </div>
                                </div>
                                <div className={styles.field}>
                                    <label>Email</label>
                                    <input
                                        type="email"
                                        value={profileForm.email}
                                        onChange={e => setProfileForm(f => ({ ...f, email: e.target.value }))}
                                        className={styles.input}
                                    />
                                </div>
                                <div className={styles.field}>
                                    <label>Phone</label>
                                    <input
                                        type="tel"
                                        value={profileForm.phone}
                                        onChange={e => setProfileForm(f => ({ ...f, phone: e.target.value }))}
                                        placeholder="+1 555 555 5555"
                                        className={styles.input}
                                    />
                                </div>
                                <div className={styles.field}>
                                    <label>Role</label>
                                    <input
                                        defaultValue={user?.role ? `${user.role.replace('_', ' ')} (read-only)` : 'read-only'}
                                        className={styles.input}
                                        disabled
                                    />
                                </div>
                                {profileMessage && (
                                    <p style={{ fontSize: 13, color: profileMessage.includes('success') ? '#10b981' : '#ef4444', margin: '4px 0 8px' }}>
                                        {profileMessage}
                                    </p>
                                )}
                                <div className={styles.actions}>
                                    <button className={styles.saveBtn} onClick={handleSaveProfile} disabled={savingProfile}>
                                        {savingProfile ? 'Saving...' : 'Save Profile'}
                                    </button>
                                </div>
                            </div>
                        )}

                        {tab === 'integrations' && (
                            <div className={styles.integrationList}>
                                {integrations.map(i => (
                                    <div key={i.id} className={styles.integrationItem}>
                                        <div className={styles.integrationLeft}>
                                            <div className={styles.integrationIcon}>
                                                {integrationIcons[i.id]}
                                            </div>
                                            <div>
                                                <div className={styles.integrationName}>{i.name}</div>
                                                <div className={styles.integrationDesc}>{i.desc}</div>
                                            </div>
                                        </div>
                                        <div className={styles.integrationActions}>
                                            {i.connected && <span className={styles.connectedBadge}>Connected</span>}
                                            <button 
                                                onClick={() => handleToggleIntegration(i.id)}
                                                disabled={connectingId === i.id}
                                                className={`${styles.connectBtn} ${i.connected ? styles.connectBtnGhost : styles.connectBtnSecondary}`}
                                            >
                                                {connectingId === i.id ? 'Connecting...' : (i.connected ? 'Disconnect' : 'Connect')}
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {tab === 'billing' && (
                            <div className={styles.billingSection}>
                                <div className={styles.planCard}>
                                    <div className={styles.planBadge}>Current Plan</div>
                                    <div className={styles.planName}>
                                        Pro <span className={styles.planPrice}>· $299/mo</span>
                                    </div>
                                    <div className={styles.planDesc}>Next billing: May 1, 2026 · Unlimited AI calls</div>
                                </div>
                                <button className={styles.upgradeBtn}>Upgrade to Enterprise</button>
                                <div className={styles.salesText}>Contact sales@callsync.ai for enterprise pricing and white-label options.</div>
                            </div>
                        )}
                    </div>
                </div>
            </div>



            {showVapiModal && (
                <div className={styles.modalOverlay}>
                    <div className={styles.modalCard}>
                        <h3>Connect Vapi Voice AI</h3>
                        <p>Enter your Vapi API key and Assistant ID from the Vapi dashboard.</p>
                        <div className={styles.form}>
                            <div className={styles.field}>
                                <label>API Key</label>
                                <input 
                                    type="password" 
                                    className={styles.input} 
                                    value={vapiData.apiKey}
                                    onChange={e => setVapiData(d => ({ ...d, apiKey: e.target.value }))}
                                />
                            </div>
                            <div className={styles.field}>
                                <label>Assistant ID (Optional)</label>
                                <input 
                                    className={styles.input} 
                                    value={vapiData.assistantId}
                                    onChange={e => setVapiData(d => ({ ...d, assistantId: e.target.value }))}
                                />
                            </div>
                        </div>
                        <div className={styles.modalActions}>
                            <button onClick={() => setShowVapiModal(false)} className={styles.cancelBtn}>Cancel</button>
                            <button onClick={handleSaveVapi} className={styles.saveBtn} disabled={isSubmitting}>
                                {isSubmitting ? 'Saving...' : 'Connect Vapi'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {showTwilioModal && (
                <div className={styles.modalOverlay}>
                    <div className={styles.modalCard}>
                        <h3>Connect Twilio SMS</h3>
                        <p>Connect your Twilio account to send SMS reminders.</p>
                        <div className={styles.form}>
                            <div className={styles.field}>
                                <label>Account SID</label>
                                <input 
                                    className={styles.input} 
                                    value={twilioData.sid}
                                    onChange={e => setTwilioData(d => ({ ...d, sid: e.target.value }))}
                                />
                            </div>
                            <div className={styles.field}>
                                <label>Auth Token</label>
                                <input 
                                    type="password" 
                                    className={styles.input} 
                                    value={twilioData.authToken}
                                    onChange={e => setTwilioData(d => ({ ...d, authToken: e.target.value }))}
                                />
                            </div>
                            <div className={styles.field}>
                                <label>Twilio Phone Number</label>
                                <input 
                                    className={styles.input} 
                                    placeholder="+1..."
                                    value={twilioData.phoneNumber}
                                    onChange={e => setTwilioData(d => ({ ...d, phoneNumber: e.target.value }))}
                                />
                            </div>
                        </div>
                        <div className={styles.modalActions}>
                            <button onClick={() => setShowTwilioModal(false)} className={styles.cancelBtn}>Cancel</button>
                            <button onClick={handleSaveTwilio} className={styles.saveBtn} disabled={isSubmitting}>
                                {isSubmitting ? 'Saving...' : 'Connect Twilio'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

