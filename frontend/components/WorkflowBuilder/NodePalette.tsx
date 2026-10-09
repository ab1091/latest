'use client';

import { ADDABLE_NODE_TYPES, NODE_TYPE_META, type NodeType } from '@/lib/workflowNodeTypes';
import styles from './WorkflowBuilder.module.css';

interface Props {
    onAdd: (nodeType: NodeType) => void;
}

export function NodePalette({ onAdd }: Props) {
    return (
        <div className={styles.palette}>
            {ADDABLE_NODE_TYPES.map((nodeType) => {
                const meta = NODE_TYPE_META[nodeType];
                const Icon = meta.icon;
                return (
                    <button key={nodeType} className={styles.paletteItem} onClick={() => onAdd(nodeType)}>
                        <span className={styles.paletteIcon} style={{ background: `${meta.color}22`, color: meta.color }}>
                            <Icon size={14} />
                        </span>
                        <span>
                            <div className={styles.paletteLabel}>{meta.label}</div>
                            <div className={styles.paletteDesc}>{meta.description}</div>
                        </span>
                    </button>
                );
            })}
        </div>
    );
}
