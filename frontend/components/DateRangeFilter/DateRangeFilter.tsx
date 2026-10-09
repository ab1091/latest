'use client';

export type DateRangeKey = 'all' | 'today' | '7d' | '30d' | '90d' | 'custom';

export interface DateRangeValue {
    key: DateRangeKey;
    from: string; // yyyy-mm-dd, only meaningful when key === 'custom'
    to: string;   // yyyy-mm-dd, only meaningful when key === 'custom'
}

export const DEFAULT_DATE_RANGE: DateRangeValue = { key: 'all', from: '', to: '' };

const RANGE_DAYS: Partial<Record<DateRangeKey, number>> = { today: 0, '7d': 7, '30d': 30, '90d': 90 };

/** Does the ISO timestamp fall within the selected range? Missing timestamps only match 'all'. */
export function inDateRange(iso: string | null | undefined, range: DateRangeValue): boolean {
    if (range.key === 'all') return true;
    if (!iso) return false;
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return false;

    if (range.key === 'custom') {
        const from = range.from ? new Date(`${range.from}T00:00:00`).getTime() : -Infinity;
        const to = range.to ? new Date(`${range.to}T23:59:59.999`).getTime() : Infinity;
        return t >= from && t <= to;
    }

    const days = RANGE_DAYS[range.key] ?? 0;
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    start.setDate(start.getDate() - days);
    return t >= start.getTime();
}

const OPTIONS: { key: DateRangeKey; label: string }[] = [
    { key: 'all', label: 'All Time' },
    { key: 'today', label: 'Today' },
    { key: '7d', label: 'Last 7 Days' },
    { key: '30d', label: 'Last 30 Days' },
    { key: '90d', label: 'Last 90 Days' },
    { key: 'custom', label: 'Custom Range...' },
];

export function DateRangeFilter({ value, onChange }: { value: DateRangeValue; onChange: (v: DateRangeValue) => void }) {
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <select
                value={value.key}
                onChange={(e) => onChange({ ...value, key: e.target.value as DateRangeKey })}
                style={{
                    padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border-default, var(--border-subtle))',
                    background: 'var(--bg-card, var(--surface-panel))', color: 'var(--text-1)', fontSize: 12.5,
                    fontWeight: 600, cursor: 'pointer',
                }}
            >
                {OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
            {value.key === 'custom' && (
                <>
                    <input
                        type="date"
                        value={value.from}
                        onChange={(e) => onChange({ ...value, from: e.target.value })}
                        style={{
                            padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-default, var(--border-subtle))',
                            background: 'var(--bg-card, var(--surface-panel))', color: 'var(--text-1)', fontSize: 12.5,
                        }}
                    />
                    <span style={{ color: 'var(--text-4)', fontSize: 12 }}>to</span>
                    <input
                        type="date"
                        value={value.to}
                        onChange={(e) => onChange({ ...value, to: e.target.value })}
                        style={{
                            padding: '6px 8px', borderRadius: 8, border: '1px solid var(--border-default, var(--border-subtle))',
                            background: 'var(--bg-card, var(--surface-panel))', color: 'var(--text-1)', fontSize: 12.5,
                        }}
                    />
                </>
            )}
        </div>
    );
}
