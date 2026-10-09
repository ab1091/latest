import {
    Play, MessageCircle, Mail, Phone, Clock, GitBranch,
    ArrowRightLeft, Tag, Bell, CheckCircle2,
} from 'lucide-react';

export type NodeType =
    | 'trigger' | 'send_sms' | 'send_email' | 'ai_call' | 'wait'
    | 'branch_condition' | 'move_stage' | 'add_tag' | 'notify_staff' | 'end';

export interface NodeTypeMeta {
    label: string;
    icon: typeof Play;
    color: string;
    description: string;
    defaultConfig: Record<string, any>;
    /** true if this node type can appear in the "add node" palette (trigger/end are structural, added automatically) */
    addable: boolean;
}

export const NODE_TYPE_META: Record<NodeType, NodeTypeMeta> = {
    trigger: {
        label: 'Trigger', icon: Play, color: '#818cf8',
        description: 'Where this workflow starts', defaultConfig: {}, addable: false,
    },
    send_sms: {
        label: 'Send SMS', icon: MessageCircle, color: '#e8c877',
        description: 'Send a text message (SMS/WhatsApp)',
        defaultConfig: { channel: 'sms', goal: '' }, addable: true,
    },
    send_email: {
        label: 'Send Email', icon: Mail, color: '#f6c969',
        description: 'Send an AI-written email via Gmail (skipped if the lead has no email on file)',
        defaultConfig: { subject: '', template_ref: '' }, addable: true,
    },
    ai_call: {
        label: 'AI Call', icon: Phone, color: '#7fded0',
        description: 'Place an outbound AI voice call',
        defaultConfig: {}, addable: true,
    },
    wait: {
        label: 'Wait', icon: Clock, color: '#89a7a1',
        description: 'Pause before the next step (must lead to Send SMS / AI Call)',
        defaultConfig: { amount: 1, unit: 'hours' }, addable: true,
    },
    branch_condition: {
        label: 'Branch', icon: GitBranch, color: '#f6a969',
        description: 'Split the path based on an outcome (replied? call confirmed?)',
        defaultConfig: { mode: 'reply_check', timeout_hours: 4, true_branch: 'replied', false_branch: 'no_reply' },
        addable: true,
    },
    move_stage: {
        label: 'Move Stage', icon: ArrowRightLeft, color: '#818cf8',
        description: 'Move the lead to a new pipeline stage',
        defaultConfig: { event: 'inbound_reply' }, addable: true,
    },
    add_tag: {
        label: 'Add Tag', icon: Tag, color: '#c084fc',
        description: 'Tag the lead', defaultConfig: { tag: '' }, addable: true,
    },
    notify_staff: {
        label: 'Notify Staff', icon: Bell, color: '#ff8f8f',
        description: 'Post a message to the live activity feed',
        defaultConfig: { message: '' }, addable: true,
    },
    end: {
        label: 'End', icon: CheckCircle2, color: '#5d7772',
        description: 'End of this path', defaultConfig: {}, addable: false,
    },
};

export const ADDABLE_NODE_TYPES = (Object.keys(NODE_TYPE_META) as NodeType[]).filter(
    (t) => NODE_TYPE_META[t].addable,
);

export const MOVE_STAGE_EVENTS = [
    { value: 'welcome_sms_sent', label: 'Welcome SMS sent → Contacted' },
    { value: 'inbound_reply', label: 'Lead replied → Connected' },
    { value: 'ai_qualified', label: 'AI qualified the lead → Connected' },
    { value: 'ai_quoted', label: 'Quote discussed → Quoted' },
    { value: 'appointment_booked', label: 'Appointment booked → Appointment Scheduled' },
    { value: 'appointment_completed', label: 'Appointment completed → Closed Won' },
    { value: 'call_outcome_confirmed', label: 'Call confirmed → Closed Won' },
    { value: 'mark_dead', label: 'Mark Dead' },
];

export const STAGE_OPTIONS = [
    { value: 'new_lead', label: 'New Lead' },
    { value: 'old_lead', label: 'Old Lead' },
    { value: 'connected', label: 'Connected' },
    { value: 'quoted', label: 'Quoted' },
    { value: 'appointment_scheduled', label: 'Appointment Scheduled' },
    { value: 'closed', label: 'Closed' },
    { value: 'dead', label: 'Trip Lead' },
];
