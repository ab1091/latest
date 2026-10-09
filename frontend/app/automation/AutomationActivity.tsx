'use client';

import { useRouter } from 'next/navigation';
import { Activity, MessageSquare, Phone, GitBranch, ArrowRightLeft, Bell, XCircle, Mail } from 'lucide-react';
import { useActivityFeed, ActivityFeedEvent } from '@/hooks/useActivityFeed';
import { parseApiDate } from '@/lib/date';
import styles from './automation.module.css';

const EVENT_ICON: Record<string, React.ElementType> = {
    stage_change: ArrowRightLeft,
    workflow_enrolled: GitBranch,
    sms_sent: MessageSquare,
    sms_failed: XCircle,
    call_placed: Phone,
    workflow_notify_staff: Bell,
    email_sent: Mail,
};

function timeAgo(iso: string): string {
    const seconds = Math.floor((Date.now() - parseApiDate(iso).getTime()) / 1000);
    if (seconds < 5) return 'just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

function EventRow({ event, onOpenLead }: { event: ActivityFeedEvent; onOpenLead: (id: string) => void }) {
    const Icon = EVENT_ICON[event.event_type] || Activity;
    const isFailure = event.event_type.endsWith('_failed');
    return (
        <div
            className={styles.card}
            style={{
                display: 'flex', alignItems: 'flex-start', gap: 12, cursor: event.lead_id ? 'pointer' : 'default',
                borderColor: isFailure ? 'var(--danger, #dc2626)' : undefined,
            }}
            onClick={() => event.lead_id && onOpenLead(event.lead_id)}
        >
            <div
                style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    width: 30, height: 30, borderRadius: 8, flexShrink: 0,
                    background: isFailure ? 'rgba(220,38,38,0.12)' : 'var(--primary-subtle)',
                    color: isFailure ? 'var(--danger, #dc2626)' : 'var(--primary-text)',
                }}
            >
                <Icon size={15} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, color: 'var(--text-1)' }}>{event.title}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text-4)', marginTop: 2 }}>{timeAgo(event.created_at)}</div>
            </div>
        </div>
    );
}

export function AutomationActivity() {
    const { events, connected } = useActivityFeed();
    const router = useRouter();
    const openLead = (id: string) => router.push(`/leads/${id}`);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5, fontWeight: 700, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                <span
                    style={{
                        width: 7, height: 7, borderRadius: '50%',
                        background: connected ? '#22c55e' : 'var(--text-4)',
                        boxShadow: connected ? '0 0 0 3px rgba(34,197,94,0.2)' : undefined,
                    }}
                />
                {connected ? 'Live' : 'Connecting…'} — every trigger as it fires
            </div>

            {events.length === 0 ? (
                <div className={styles.emptyState}>
                    <Activity size={36} strokeWidth={1.2} />
                    <p>No automation activity yet. Stage changes, workflow enrollments, and automated sends/calls will show up here in real time.</p>
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {events.map(event => (
                        <EventRow key={event.id} event={event} onOpenLead={openLead} />
                    ))}
                </div>
            )}
        </div>
    );
}
