'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CreditCard } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { parseApiDate } from '@/lib/date';
import { SideNav } from '@/components/SideNav/SideNav';
import { hasModuleAccess } from '@/lib/permissions';
import styles from './billing.module.css';

interface Plan {
    id: string; name: string; price_cents: number; billing_interval: string;
    max_staff_users: number | null; max_leads: number | null; features: Record<string, any>;
}
interface Subscription {
    plan_id: string; plan_name: string; status: string; price_cents: number;
    current_period_end: string;
}

export default function BillingPage() {
    const { accessToken, isLoading, user } = useAuth();
    const router = useRouter();
    const [plans, setPlans] = useState<Plan[]>([]);
    const [subscription, setSubscription] = useState<Subscription | null>(null);
    const [changing, setChanging] = useState(false);

    useEffect(() => {
        if (isLoading) return;
        if (!accessToken) { router.replace('/login'); return; }
        if (user && !['admin', 'super_admin'].includes(user.role) && !hasModuleAccess(user, 'billing', 'admin')) router.replace('/leads');
    }, [isLoading, accessToken, user, router]);

    const load = useCallback(async () => {
        if (!accessToken) return;
        const headers = { Authorization: `Bearer ${accessToken}` };
        const [plansRes, subRes] = await Promise.all([
            fetch('/api/billing/plans', { headers }).then(r => r.json()),
            fetch('/api/billing/subscription', { headers }).then(r => r.json()),
        ]);
        if (plansRes.success) setPlans(plansRes.data.plans);
        if (subRes.success) setSubscription(subRes.data.subscription);
    }, [accessToken]);

    useEffect(() => { load(); }, [load]);

    const changePlan = async (planId: string) => {
        if (!accessToken) return;
        setChanging(true);
        try {
            await fetch('/api/billing/subscription', {
                method: 'PATCH',
                headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ plan_id: planId }),
            });
            load();
        } catch {}
        setChanging(false);
    };

    const fmtPrice = (cents: number) => cents === 0 ? 'Free' : `$${(cents / 100).toFixed(0)}`;

    return (
        <div className={styles.page}>
            <SideNav />
            <div className={styles.main}>
                <div className={styles.header}>
                    <div className={styles.headerIcon}><CreditCard size={22} /></div>
                    <div className={styles.headerInfo}>
                        <h1>Billing</h1>
                        <p>Plans, subscription status, and usage limits for your agency.</p>
                    </div>
                </div>

                {subscription && (
                    <div className={styles.currentCard}>
                        <div>
                            <div className={styles.currentPlanName}>
                                {subscription.plan_name} Plan
                                <span className={styles.statusPill}>{subscription.status}</span>
                            </div>
                            <div style={{ fontSize: 12.5, color: 'var(--text-3)', marginTop: 6 }}>
                                {fmtPrice(subscription.price_cents)}/mo · renews {parseApiDate(subscription.current_period_end).toLocaleDateString()}
                            </div>
                        </div>
                    </div>
                )}

                <div className={styles.stubNote}>
                    Changing your plan here updates it immediately — no payment is charged yet (Stripe integration is planned).
                </div>

                <div className={styles.planGrid}>
                    {plans.map(plan => {
                        const isActive = subscription?.plan_id === plan.id;
                        return (
                            <div key={plan.id} className={`${styles.planCard} ${isActive ? styles.planCardActive : ''}`}>
                                <div className={styles.planName}>{plan.name}</div>
                                <div className={styles.planPrice}>
                                    {fmtPrice(plan.price_cents)}{plan.price_cents > 0 && <span>/mo</span>}
                                </div>
                                <div className={styles.planFeatures}>
                                    <div>{plan.max_staff_users ?? 'Unlimited'} staff users</div>
                                    <div>{plan.max_leads ?? 'Unlimited'} leads</div>
                                    <div>{plan.features?.ai_agents ?? 'Unlimited'} AI agents</div>
                                    <div>{plan.features?.workflows ?? 'Unlimited'} workflows</div>
                                    <div>{plan.features?.sms_included ?? 'Unlimited'} SMS included</div>
                                </div>
                                <button
                                    className={`${styles.planBtn} ${isActive ? styles.planBtnActive : ''}`}
                                    onClick={() => !isActive && changePlan(plan.id)}
                                    disabled={isActive || changing}
                                >
                                    {isActive ? 'Current Plan' : 'Switch to this plan'}
                                </button>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
