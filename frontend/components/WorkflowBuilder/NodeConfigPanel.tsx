'use client';

import { X, Trash2 } from 'lucide-react';
import { NODE_TYPE_META, MOVE_STAGE_EVENTS, type NodeType } from '@/lib/workflowNodeTypes';
import type { WorkflowNodeData } from './WorkflowNode';
import styles from './WorkflowBuilder.module.css';

interface Props {
    nodeKey: string;
    data: WorkflowNodeData;
    onChange: (config: Record<string, any>) => void;
    onDelete: () => void;
    onClose: () => void;
}

export function NodeConfigPanel({ nodeKey, data, onChange, onDelete, onClose }: Props) {
    const nodeType = data.nodeType;
    const config = data.config || {};
    const meta = NODE_TYPE_META[nodeType];
    const set = (patch: Record<string, any>) => onChange({ ...config, ...patch });

    return (
        <div style={{
            position: 'absolute', top: 0, right: 0, bottom: 0, width: 300,
            background: 'var(--bg-raised)', borderLeft: '1px solid var(--border-default)',
            padding: '18px 16px', overflowY: 'auto', zIndex: 10,
        }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>{meta.label}</div>
                    <div style={{ fontSize: 10.5, color: 'var(--text-4)' }}>{nodeKey}</div>
                </div>
                <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer' }}>
                    <X size={16} />
                </button>
            </div>

            <p style={{ fontSize: 11.5, color: 'var(--text-3)', marginBottom: 14, lineHeight: 1.4 }}>{meta.description}</p>

            <div className={styles.configPanel}>
                {nodeType === 'wait' && (
                    <div className={styles.configRow}>
                        <div className={styles.configField}>
                            <label>Amount</label>
                            <input type="number" min={0} value={config.amount ?? 0}
                                onChange={e => set({ amount: Number(e.target.value) })} />
                        </div>
                        <div className={styles.configField}>
                            <label>Unit</label>
                            <select value={config.unit ?? 'minutes'} onChange={e => set({ unit: e.target.value })}>
                                <option value="minutes">Minutes</option>
                                <option value="hours">Hours</option>
                                <option value="days">Days</option>
                            </select>
                        </div>
                    </div>
                )}

                {nodeType === 'send_sms' && (
                    <>
                        <div className={styles.configField}>
                            <label>Channel</label>
                            <select value={config.channel ?? 'sms'} onChange={e => set({ channel: e.target.value })}>
                                <option value="sms">SMS</option>
                                <option value="whatsapp">WhatsApp</option>
                            </select>
                        </div>
                        <div className={styles.configField}>
                            <label>Message goal (what should this step accomplish?)</label>
                            <textarea value={config.goal ?? ''} onChange={e => set({ goal: e.target.value })}
                                placeholder="e.g. Day 2 nudge — they haven't replied, gently check in without repeating Day 1" />
                        </div>
                    </>
                )}

                {nodeType === 'send_email' && (
                    <>
                        <div className={styles.configField}>
                            <label>Subject</label>
                            <input value={config.subject ?? ''} onChange={e => set({ subject: e.target.value })} />
                        </div>
                        <p style={{ fontSize: 11, color: 'var(--text-4)' }}>
                            Skipped automatically for leads with no real email on file (SMS/call-only leads).
                        </p>
                    </>
                )}

                {nodeType === 'branch_condition' && (
                    <>
                        <div className={styles.configField}>
                            <label>Evaluate</label>
                            <select value={config.mode ?? 'reply_check'} onChange={e => set({ mode: e.target.value })}>
                                <option value="reply_check">Did the lead reply?</option>
                                <option value="last_result">Previous step&apos;s outcome</option>
                            </select>
                        </div>
                        {config.mode === 'reply_check' ? (
                            <div className={styles.configRow}>
                                <div className={styles.configField}>
                                    <label>Wait up to</label>
                                    <input type="number" min={0}
                                        value={config.timeout_unit === 'minutes'
                                            ? Math.round((config.timeout_hours ?? 4) * 60)
                                            : (config.timeout_hours ?? 4)}
                                        onChange={e => {
                                            const raw = Number(e.target.value);
                                            const unit = config.timeout_unit === 'minutes' ? 'minutes' : 'hours';
                                            set({ timeout_hours: unit === 'minutes' ? raw / 60 : raw, timeout_unit: unit });
                                        }} />
                                </div>
                                <div className={styles.configField}>
                                    <label>Unit</label>
                                    <select value={config.timeout_unit ?? 'hours'}
                                        onChange={e => set({ timeout_unit: e.target.value })}>
                                        <option value="minutes">Minutes</option>
                                        <option value="hours">Hours</option>
                                    </select>
                                </div>
                            </div>
                        ) : (
                            <div className={styles.configRow}>
                                <div className={styles.configField}>
                                    <label>Field</label>
                                    <input value={config.field ?? 'outcome'} onChange={e => set({ field: e.target.value })} />
                                </div>
                                <div className={styles.configField}>
                                    <label>Equals</label>
                                    <input value={config.equals ?? ''} onChange={e => set({ equals: e.target.value })} />
                                </div>
                            </div>
                        )}
                        <div className={styles.configRow}>
                            <div className={styles.configField}>
                                <label>True branch label</label>
                                <input value={config.true_branch ?? 'yes'} onChange={e => set({ true_branch: e.target.value })} />
                            </div>
                            <div className={styles.configField}>
                                <label>False branch label</label>
                                <input value={config.false_branch ?? 'no'} onChange={e => set({ false_branch: e.target.value })} />
                            </div>
                        </div>
                    </>
                )}

                {nodeType === 'move_stage' && (
                    <div className={styles.configField}>
                        <label>Event</label>
                        <select value={config.event ?? ''} onChange={e => set({ event: e.target.value })}>
                            <option value="">Select an event…</option>
                            {MOVE_STAGE_EVENTS.map(ev => <option key={ev.value} value={ev.value}>{ev.label}</option>)}
                        </select>
                    </div>
                )}

                {nodeType === 'add_tag' && (
                    <div className={styles.configField}>
                        <label>Tag</label>
                        <input value={config.tag ?? ''} onChange={e => set({ tag: e.target.value })} placeholder="e.g. hot-lead" />
                    </div>
                )}

                {nodeType === 'notify_staff' && (
                    <div className={styles.configField}>
                        <label>Message</label>
                        <textarea value={config.message ?? ''} onChange={e => set({ message: e.target.value })}
                            placeholder="Shown in the live activity feed" />
                    </div>
                )}

                {(nodeType === 'trigger' || nodeType === 'end') && (
                    <div style={{ fontSize: 11.5, color: 'var(--text-4)' }}>This is a structural node — nothing to configure.</div>
                )}
            </div>

            {nodeType !== 'trigger' && nodeType !== 'end' && (
                <button
                    onClick={onDelete}
                    style={{
                        marginTop: 20, display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center',
                        width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--status-danger-bg)',
                        background: 'var(--status-danger-bg)', color: 'var(--status-danger)', cursor: 'pointer',
                        fontSize: 12, fontWeight: 600,
                    }}
                >
                    <Trash2 size={13} /> Delete node
                </button>
            )}
        </div>
    );
}
