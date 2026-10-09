'use client';

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { NODE_TYPE_META, type NodeType } from '@/lib/workflowNodeTypes';
import styles from './WorkflowBuilder.module.css';

export interface WorkflowNodeData {
    nodeType: NodeType;
    config: Record<string, any>;
    label?: string;
    [key: string]: unknown;
}

function summarize(nodeType: NodeType, config: Record<string, any>): string {
    switch (nodeType) {
        case 'wait':
            return `${config.amount ?? 0} ${config.unit ?? 'minutes'}`;
        case 'send_sms': {
            const fallback = config.channel === 'whatsapp' ? 'WhatsApp message' : 'SMS message';
            if (!config.goal) return fallback;
            return config.goal.length > 60 ? `${config.goal.slice(0, 60)}…` : config.goal;
        }
        case 'branch_condition':
            return config.mode === 'reply_check'
                ? `replied within ${config.timeout_hours ?? 4}h?`
                : `${config.field ?? 'outcome'} = ${config.equals ?? '?'}`;
        case 'move_stage':
            return config.event || 'select an event';
        case 'add_tag':
            return config.tag ? `tag: ${config.tag}` : 'no tag set';
        case 'notify_staff':
            return config.message || 'no message set';
        default:
            return '';
    }
}

export function WorkflowNode({ data, selected }: NodeProps) {
    const nodeData = data as unknown as WorkflowNodeData;
    const meta = NODE_TYPE_META[nodeData.nodeType];
    const Icon = meta.icon;
    const isBranch = nodeData.nodeType === 'branch_condition';
    const isTrigger = nodeData.nodeType === 'trigger';
    const isEnd = nodeData.nodeType === 'end';
    const summary = summarize(nodeData.nodeType, nodeData.config || {});

    return (
        <div className={`${styles.node} ${selected ? styles.nodeSelected : ''}`} style={{ borderColor: selected ? meta.color : undefined }}>
            {!isTrigger && <Handle type="target" position={Position.Left} className={styles.handle} />}
            <div className={styles.nodeHeader}>
                <span className={styles.nodeIcon} style={{ background: `${meta.color}22`, color: meta.color }}>
                    <Icon size={14} />
                </span>
                <span className={styles.nodeLabel}>{meta.label}</span>
            </div>
            {summary && <div className={styles.nodeSummary}>{summary}</div>}

            {isBranch ? (
                <div className={styles.branchHandles}>
                    <div className={styles.branchHandleRow}>
                        <span className={styles.branchTag} style={{ color: 'var(--status-success)' }}>{nodeData.config?.true_branch || 'yes'}</span>
                        <Handle type="source" position={Position.Right} id="true" style={{ position: 'relative', transform: 'none', right: 0 }} className={styles.handle} />
                    </div>
                    <div className={styles.branchHandleRow}>
                        <span className={styles.branchTag} style={{ color: 'var(--status-danger)' }}>{nodeData.config?.false_branch || 'no'}</span>
                        <Handle type="source" position={Position.Right} id="false" style={{ position: 'relative', transform: 'none', right: 0 }} className={styles.handle} />
                    </div>
                </div>
            ) : !isEnd ? (
                <Handle type="source" position={Position.Right} className={styles.handle} />
            ) : null}
        </div>
    );
}

export const NODE_TYPES = { workflowNode: WorkflowNode };
