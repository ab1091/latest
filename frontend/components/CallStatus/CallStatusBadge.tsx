'use client';

// CallStatusBadge — Tayyba's frontend component
// Shows AI call outcome on appointment cards in the dashboard.

interface CallStatusBadgeProps {
    outcome: 'confirmed' | 'cancelled' | 'reschedule_requested' | 'no_answer' | 'voicemail' | 'failed' | null;
    summary?: string | null;
    durationSeconds?: number | null;
}

const OUTCOME_CONFIG = {
    confirmed: {
        label: 'Confirmed via AI Call',
        color: 'var(--status-success)',
        bg: 'var(--status-success-bg)',
        icon: '✓',
    },
    cancelled: {
        label: 'Cancelled via AI Call',
        color: 'var(--status-danger)',
        bg: 'var(--status-danger-bg)',
        icon: '✕',
    },
    reschedule_requested: {
        label: 'Reschedule Requested',
        color: 'var(--status-warning)',
        bg: 'var(--status-warning-bg)',
        icon: '↺',
    },
    no_answer: {
        label: 'No Answer',
        color: 'var(--text-3)',
        bg: 'rgba(137, 167, 161, 0.12)',
        icon: '○',
    },
    voicemail: {
        label: 'Voicemail Left',
        color: 'var(--primary-text)',
        bg: 'rgba(109, 231, 211, 0.12)',
        icon: '◉',
    },
    failed: {
        label: 'Call Failed',
        color: 'var(--status-danger)',
        bg: 'var(--status-danger-bg)',
        icon: '!',
    },
};

export function CallStatusBadge({ outcome, summary, durationSeconds }: CallStatusBadgeProps) {
    if (!outcome) return null;

    const cfg = OUTCOME_CONFIG[outcome];

    return (
        <div style={{ marginTop: '8px' }}>
            {/* Badge */}
            <span
                style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '3px 10px',
                    borderRadius: '99px',
                    fontSize: '12px',
                    fontWeight: 600,
                    color: cfg.color,
                    background: cfg.bg,
                    border: `1px solid ${cfg.color}33`,
                }}
            >
                <span>{cfg.icon}</span>
                {cfg.label}
                {durationSeconds && (
                    <span style={{ opacity: 0.7, fontWeight: 400 }}>
                        · {Math.round(durationSeconds / 60)}m {durationSeconds % 60}s
                    </span>
                )}
            </span>

            {/* Summary */}
            {summary && (
                <p
                    style={{
                        marginTop: '6px',
                        fontSize: '12px',
                        color: 'var(--text-3)',
                        fontStyle: 'italic',
                        lineHeight: 1.4,
                    }}
                >
                    &ldquo;{summary}&rdquo;
                </p>
            )}
        </div>
    );
}
