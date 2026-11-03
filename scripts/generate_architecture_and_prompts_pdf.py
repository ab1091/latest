#!/usr/bin/env python3
"""
generate_architecture_and_prompts_pdf.py

Compiles the Complete System Architecture, Execution Flow, Persona System Prompts,
and Action Execution Engine into an executive-grade, beautifully styled PDF document.

Includes:
- System Architecture Diagram & Component Responsibilities
- End-to-End Data Flow (Ingestion to Calendar Booking)
- Verbatim Master System Prompt for Alex (AI Intake Specialist)
- 4 High-Converting AI Outreach Hooks
- 7 Backend Action Execution Specifications
- Full Lead Lifecycle State Machine Matrix
- Verification & Operational Endpoints

Strict typography: Zero em dashes, zero en dashes, zero double hyphens.
"""

import os
import sys
import html
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

# Palette Definition
NAVY_PRIMARY = colors.HexColor("#0B192C")      # Deep Slate Navy
NAVY_SECONDARY = colors.HexColor("#1E3A8A")    # Deep Royal Blue
TECH_BLUE = colors.HexColor("#2563EB")         # Electric Tech Blue
CYAN_ACCENT = colors.HexColor("#0284C7")       # Cyan highlight
BG_LIGHT = colors.HexColor("#F8FAFC")          # Slate 50
BG_CODE = colors.HexColor("#0F172A")           # Dark Slate for prompt blocks
BORDER_COLOR = colors.HexColor("#CBD5E1")      # Slate 300
BORDER_LIGHT = colors.HexColor("#E2E8F0")      # Slate 200
TEXT_DARK = colors.HexColor("#0F172A")         # Body dark slate
TEXT_MUTED = colors.HexColor("#475569")        # Muted secondary text
SUCCESS_BG = colors.HexColor("#DCFCE7")        # Light green
SUCCESS_TXT = colors.HexColor("#166534")       # Dark green
WARN_BG = colors.HexColor("#FEF3C7")           # Light amber
WARN_TXT = colors.HexColor("#92400E")          # Dark amber

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and stamp total page count,
    running header with branding, and running footer with confidentiality notice.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        
        # Suppress running header on cover page
        if self._pageNumber > 1:
            self.setStrokeColor(BORDER_COLOR)
            self.setLineWidth(0.6)
            self.line(36, 756, 576, 756)
            
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(NAVY_PRIMARY)
            self.drawString(36, 762, "ALLZONE TECHNOLOGIES")
            
            self.setFont("Helvetica", 7.5)
            self.setFillColor(TEXT_MUTED)
            self.drawString(145, 762, "|   AI Funnel Architecture, Flow & Persona Blueprint")
            
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(TECH_BLUE)
            self.drawRightString(576, 762, "PRODUCTION SPECIFICATION")

        # Footer on all pages
        self.setStrokeColor(BORDER_COLOR)
        self.setLineWidth(0.6)
        self.line(36, 40, 576, 40)
        
        self.setFont("Helvetica", 7.5)
        self.setFillColor(TEXT_MUTED)
        self.drawString(36, 29, "Confidential & Proprietary   |   AllZone Technologies Inc. (allzonetech.com)   |   San Jose, CA")
        
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(NAVY_PRIMARY)
        self.drawRightString(576, 29, page_str)
        
        self.restoreState()

def clean(text):
    """Clean text from prohibited dashes and escape HTML."""
    if not text:
        return ""
    t = text.replace("—", ", ").replace("–", "-").replace("--", "-")
    return html.escape(t)

def build_pdf(output_filename):
    print(f"Generating AllZone Architecture & Prompts PDF: {output_filename}")
    
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=42,
        bottomMargin=45
    )
    
    base_styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=base_styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=NAVY_PRIMARY,
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        textColor=TECH_BLUE,
        spaceAfter=14
    )
    
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=base_styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=NAVY_PRIMARY,
        spaceBefore=14,
        spaceAfter=6
    )

    sub_heading = ParagraphStyle(
        "SubHeading",
        parent=base_styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=NAVY_SECONDARY,
        spaceBefore=8,
        spaceAfter=4
    )
    
    body_style = ParagraphStyle(
        "BodyDark",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=TEXT_DARK
    )
    
    body_muted = ParagraphStyle(
        "BodyMuted",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=TEXT_MUTED
    )
    
    meta_key = ParagraphStyle(
        "MetaKey",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=NAVY_PRIMARY
    )
    
    meta_val = ParagraphStyle(
        "MetaVal",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=TEXT_DARK
    )

    code_text = ParagraphStyle(
        "CodeText",
        parent=base_styles["Normal"],
        fontName="Courier",
        fontSize=7.2,
        leading=9.5,
        textColor=colors.HexColor("#0F172A")
    )

    code_box_text = ParagraphStyle(
        "CodeBoxText",
        parent=base_styles["Normal"],
        fontName="Courier",
        fontSize=7.2,
        leading=10,
        textColor=colors.HexColor("#E2E8F0")
    )
    
    story = []
    
    # ---------------------------------------------------------
    # COVER / HEADER
    # ---------------------------------------------------------
    brand_table = Table(
        [
            [
                Paragraph("<b>ALLZONE TECHNOLOGIES</b><br/><font size=7 color='#64748B'>PRODUCTION AI & AGENTIC SYSTEMS ENGINEERING</font>", title_style),
                Paragraph("<font size=8><b>Web:</b> allzonetech.com<br/><b>Inquiries:</b> services@allzonetech.com<br/><b>Direct:</b> +1 (408) 850-5081<br/><b>HQ:</b> San Jose, California</font>", body_muted)
            ]
        ],
        colWidths=[360, 180]
    )
    brand_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(brand_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY_PRIMARY, spaceBefore=4, spaceAfter=12))
    
    story.append(Paragraph("AI Lead Funnel: Architecture, Execution Flow & Persona Blueprint", title_style))
    story.append(Paragraph("Complete Technical Specifications: Microservices, Funnel State Machine, Production Prompts, and Action Execution Engine", subtitle_style))
    
    meta_summary = [
        [
            Paragraph("<b>Target Autonomous Agent:</b> Alex (AI Solutions Specialist)", meta_key),
            Paragraph("<b>Target Services:</b> 100% Pure AI Services & Agentic Systems", meta_key)
        ],
        [
            Paragraph("<b>Core Backend Services:</b> crm-service (8003), ai-service (8002), frontend (3001)", meta_key),
            Paragraph("<b>Database:</b> PostgreSQL 14 (aicrm, UTF-8, Schema v41)", meta_key)
        ],
        [
            Paragraph("<b>Outbound Safeguards:</b> Circuit Breaker (20/hr, 50/day), 9am-5:30pm Window", meta_key),
            Paragraph("<b>Compliance:</b> Zero Company Name in SMS, No Em Dashes, TCPA STOP Compliant", meta_key)
        ]
    ]
    meta_summary_tbl = Table(meta_summary, colWidths=[270, 270])
    meta_summary_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(meta_summary_tbl)
    story.append(Spacer(1, 10))
    
    # ---------------------------------------------------------
    # SECTION 1: SYSTEM ARCHITECTURE
    # ---------------------------------------------------------
    story.append(Paragraph("1. System Architecture & Microservices Topology", section_heading))
    story.append(Paragraph(
        "The system operates as an event-driven microservices architecture optimized for sub-second conversational latency, "
        "strict rate-limiting, and automated calendar conversion. The platform comprises three core microservices, "
        "a persistent PostgreSQL state ledger, an outbound velocity pacer, and multi-channel external gateways.",
        body_style
    ))
    story.append(Spacer(1, 6))
    
    arch_table_data = [
        [
            Paragraph("<b>Component</b>", meta_key),
            Paragraph("<b>Port / Tech</b>", meta_key),
            Paragraph("<b>Operational Role & Architecture Responsibilities</b>", meta_key)
        ],
        [
            Paragraph("<b>frontend</b>", meta_val),
            Paragraph("Port 3001<br/>Next.js 14, React", meta_val),
            Paragraph("Real-time Kanban lead pipeline, interactive multi-turn chat inspector, lead detail audit views, activity feed toasts.", meta_val)
        ],
        [
            Paragraph("<b>crm-service</b>", meta_val),
            Paragraph("Port 8003<br/>FastAPI, psycopg2", meta_val),
            Paragraph("Single source of truth for leads, conversations, messages, stage mutations, immutable status history, and Server-Sent Event (SSE) stream.", meta_val)
        ],
        [
            Paragraph("<b>ai-service</b>", meta_val),
            Paragraph("Port 8002<br/>FastAPI, httpx", meta_val),
            Paragraph("LLM inference orchestrator (Llama 3.1 8B Instant & GPT-4o), prompt injection guardrails, TCPA stop filter, JSON appointment extractor, Google Calendar API integration.", meta_val)
        ],
        [
            Paragraph("<b>PostgreSQL</b>", meta_val),
            Paragraph("Port 5432<br/>DB: aicrm (UTF-8)", meta_val),
            Paragraph("Relational persistence: leads, conversations, messages, ai_agents, business_automation_settings, lead_status_history, scheduled_callbacks.", meta_val)
        ],
        [
            Paragraph("<b>Campaign Pacer</b>", meta_val),
            Paragraph("CLI Daemon<br/>run_humanoid_campaign_pacer.py", meta_val),
            Paragraph("Autonomous velocity controller. Enforces business hours (9:00 AM - 5:30 PM), queries circuit breaker (<20/hr, <50/day), selects leads, and rotates AI hooks.", meta_val)
        ],
        [
            Paragraph("<b>Gateways</b>", meta_val),
            Paragraph("Twilio, Claw, GCal", meta_val),
            Paragraph("Multi-channel carrier SMS/iMessage routing, inbound webhook receivers, Google Calendar v3 OAuth event creator, Gmail ICS dispatcher.", meta_val)
        ]
    ]
    arch_table = Table(arch_table_data, colWidths=[90, 95, 355])
    arch_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(arch_table)
    story.append(Spacer(1, 10))
    
    # ---------------------------------------------------------
    # SECTION 2: END-TO-END FUNNEL FLOW
    # ---------------------------------------------------------
    story.append(Paragraph("2. End-to-End Funnel Data Flow (Lead Ingestion to Booked Call)", section_heading))
    story.append(Paragraph(
        "The AI Tech Funnel follows a deterministic 6-phase journey from the moment a lead enters the database to the confirmation of an architecture discovery appointment:",
        body_style
    ))
    story.append(Spacer(1, 6))
    
    flow_steps = [
        [
            Paragraph("<b>Phase</b>", meta_key),
            Paragraph("<b>Trigger & Execution Mechanism</b>", meta_key),
            Paragraph("<b>Output / State Change</b>", meta_key)
        ],
        [
            Paragraph("<b>1. Ingestion</b>", meta_val),
            Paragraph("Lead uploaded via CSV batch import, web form, or API into `leads` table.", meta_val),
            Paragraph("Stage: `new_lead`<br/>Sub-status: `new`", meta_val)
        ],
        [
            Paragraph("<b>2. Pacing & Safety</b>", meta_val),
            Paragraph("Campaign Pacer evaluates queue. Verifies current time (9:00 AM - 5:30 PM) and checks `ai-service/api/sms/safety-status` for hourly limits (<20/hr).", meta_val),
            Paragraph("Pacing Approval Granted<br/>Circuit Breaker: CLOSED", meta_val)
        ],
        [
            Paragraph("<b>3. AI Hook Dispatch</b>", meta_val),
            Paragraph("Pacer dynamically selects targeted AI hook (Agentic AI, LLMOps, AI Agents for Business) and posts to `/api/conversations/{id}/messages`.", meta_val),
            Paragraph("Stage: `attempted_contact`<br/>Sub-status: `outreach_sent`", meta_val)
        ],
        [
            Paragraph("<b>4. Inbound Webhook</b>", meta_val),
            Paragraph("Lead replies over SMS. Webhook lands at `ai-service/api/sms/router.py`. Inbound message saved to DB. Checked for TCPA keywords (STOP, unsubscribe).", meta_val),
            Paragraph("Message Saved (role='user')<br/>Stage: `engaged`", meta_val)
        ],
        [
            Paragraph("<b>5. LLM Inference</b>", meta_val),
            Paragraph("Assembles system prompt, guardrails, and conversation history. Invokes Llama 3.1 / GPT-4o. Enforces zero company name mentions and no em dashes.", meta_val),
            Paragraph("Agent SMS Reply Dispatched<br/>Peer Diagnosis Delivered", meta_val)
        ],
        [
            Paragraph("<b>6. Booking & Sync</b>", meta_val),
            Paragraph("Lead confirms day, time, and email. `_check_call_confirmation` parses intent via JSON mode. Google Calendar API creates Meet event and emails invite.", meta_val),
            Paragraph("Stage: `call_scheduled`<br/>Sub-status: `appointment_confirmed`", meta_val)
        ]
    ]
    flow_table = Table(flow_steps, colWidths=[90, 310, 140])
    flow_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(flow_table)
    
    story.append(PageBreak())
    
    # ---------------------------------------------------------
    # SECTION 3: MASTER SYSTEM PROMPTS & GUARDRAILS
    # ---------------------------------------------------------
    story.append(Paragraph("3. Verbatim Production Prompts & Non-Negotiable Guardrails", section_heading))
    story.append(Paragraph(
        "Below is the exact production system prompt committed to PostgreSQL (`ai_agents` table, `agent_b9674fd6e390`), "
        "executed dynamically on every conversation turn:",
        body_style
    ))
    story.append(Spacer(1, 6))
    
    prompt_p1 = (
        "You are Alex, an AI Solutions Consultant at AllZone Technologies (www.allzonetech.com).\n"
        "AllZone engineers production-grade AI systems, agentic workflows, custom LLM operations, and scalable software architectures.\n\n"
        "YOUR PRIMARY MISSION: THE ALLZONE AI TECH FUNNEL\n"
        "You act as an intelligent, peer-level technical intake funnel. When leads interact with our campaign, your goal is to:\n"
        "1. Identify their exact AI or LLM pain point or active initiative.\n"
        "2. Provide sharp, credible technical insights demonstrating AllZone's production engineering mastery.\n"
        "3. Pivot smoothly and book a 20-30 minute Discovery / Architecture Session with our Chief AI Architect.\n\n"
        "1. CORE AI DOMAINS & HOOK TOPICS (STRICTLY PURE AI SERVICES):\n"
        "   - Agentic AI Workflows: multi-agent orchestration (LangGraph, CrewAI, AutoGen, Temporal), tool-calling reliability, dynamic memory, loop prevention, deterministic verification gates.\n"
        "   - Custom LLM Operations (LLMOps): domain fine-tuning (LoRA/QLoRA), model quantization, inference acceleration (vLLM, TensorRT-LLM), cost and latency reduction, private self-hosted deployments (Llama 3, Mistral, DeepSeek).\n"
        "   - AI Agents for Business: autonomous customer service agents, streaming voice AI (<500ms latency), intelligent document reasoning, automated workflow copilots.\n"
        "   - Enterprise RAG & Knowledge Graphs: hallucination reduction, hybrid dense/sparse vector search, GraphRAG, rerankers, deterministic citation verifiers.\n"
        "   - Computer Vision & Generative AI Pipelines: custom diffusion models, automated video/audio AI pipelines, synthetic data generation.\n\n"
        "2. FUNNEL CONVERSATION STAGES:\n"
        "   - Stage 1 (Diagnose): When a lead replies to an outreach hook (e.g. asking about agentic AI or custom LLM ops), validate their technical challenge. Ask 1 sharp question about their model latency, hallucination rate, token costs, or orchestration stack.\n"
        "   - Stage 2 (Credibility): Share 1 concise technical insight on how our engineering team solves that in production (e.g. 'We implement deterministic verification loops with LangGraph state machines so the agent never gets trapped in recursive loops').\n"
        "   - Stage 3 (The Booking Pivot): Suggest a brief architecture consultation: 'Let us set up a quick 20-minute technical session with our Chief AI Architect to look at your pipeline and architecture. Are you free Thursday afternoon or Friday morning?'\n"
        "   - Stage 4 (Appointment Locking): Confirm the exact clock time and timezone, and ask for their preferred email address to send the calendar invite."
    )
    prompt_tbl1 = Table([[Paragraph(clean(prompt_p1).replace('\n', '<br/>'), code_box_text)]], colWidths=[540])
    prompt_tbl1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_CODE),
        ('BOX', (0,0), (-1,-1), 1, TECH_BLUE),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(prompt_tbl1)
    story.append(Spacer(1, 8))
    
    prompt_p2 = (
        "3. TONE & COMMUNICATION RULES (STRICT NON-NEGOTIABLE):\n"
        "   - STRICT AI FOCUS RULE: We provide PURE AI SERVICES. NEVER pitch generic web development, IT outsourcing, or staffing ('external engineering horsepower', 'staff augmentation', 'dev shop'). Position us exclusively as elite Production AI & Agentic Systems Engineers.\n"
        "   - CRITICAL RULE: NEVER mention the company name 'AllZone Technologies' or 'AllZone' in any outgoing message to a lead. Never say 'Alex with AllZone Technologies' or 'AllZone Technologies.' in messages. Always say 'Alex here' or 'Alex', and refer to 'our engineering team', 'our Chief AI Architect', or 'our solutions team'. Real tech peers texting each other never use agency company names in cold outreach.\n"
        "   - Write like a sharp, friendly, authentic tech professional texting a peer on mobile. Never sound like a corporate support bot.\n"
        "   - Keep messages short (1-3 concise sentences for SMS/iMessage).\n"
        "   - Use natural contractions (I will -> I'll, we are -> we're, that is -> that's).\n"
        "   - CRITICAL FORMATTING RULE: NEVER use em dashes, en dashes, or double hyphens anywhere. Real engineers texting on phones never use em dashes. Use commas, periods, or single hyphens instead.\n"
        "   - Maximum 1 light, natural emoji per message where it fits naturally. Zero emojis for serious technical, security, or opt-out messages.\n"
        "   - Match the user's energy and technical depth (curious, technical, direct, skeptical, or busy).\n\n"
        "4. WRONG NUMBER / UNINTENDED RECIPIENT (FUNKY PIVOT):\n"
        "   - If someone says they are the wrong person or wrong number:\n"
        "   - Lightheartedly acknowledge the mix-up with humor (e.g. wires got crossed, digital carrier pigeon took a detour).\n"
        "   - Playfully ask if fate connected you because their company is secretly building AI agents or custom LLM systems, or if you should vanish back into the digital sunset.\n"
        "   - If they are annoyed or say STOP, immediately apologize politely with zero sales pitch and suppress their number.\n\n"
        "5. REGULATORY & COMPLIANCE:\n"
        "   - If someone says STOP, UNSUBSCRIBE, or expresses hostility: Immediately apologize politely with zero sales pitch and confirm they are unsubscribed."
    )
    prompt_tbl2 = Table([[Paragraph(clean(prompt_p2).replace('\n', '<br/>'), code_box_text)]], colWidths=[540])
    prompt_tbl2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_CODE),
        ('BOX', (0,0), (-1,-1), 1, TECH_BLUE),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(prompt_tbl2)
    story.append(Spacer(1, 10))
    
    # ---------------------------------------------------------
    # SECTION 4: OUTREACH HOOKS
    # ---------------------------------------------------------
    story.append(Paragraph("4. Production AI Services Outreach Hooks", sub_heading))
    hooks_data = [
        [
            Paragraph("<b>Target Domain</b>", meta_key),
            Paragraph("<b>Exact Text Dispatched to Lead (run_humanoid_campaign_pacer.py)</b>", meta_key)
        ],
        [
            Paragraph("<b>Agentic AI Bottlenecks</b>", meta_val),
            Paragraph("\"Hey {first_name}, Alex here. Are you facing any bottlenecks or loop issues with Agentic AI in your current tech stack? Reaching out to see if we can help streamline your agent architecture.\"", meta_val)
        ],
        [
            Paragraph("<b>Custom LLMOps & Latency</b>", meta_val),
            Paragraph("\"Hey {first_name}, Alex here. Quick question: does your team need custom LLM operations, fine-tuning, or latency optimization to cut down API costs?\"", meta_val)
        ],
        [
            Paragraph("<b>AI Agents for Business</b>", meta_val),
            Paragraph("\"Hi {first_name}, Alex here. Are you currently focusing on developing AI agents or automated copilots for your business this quarter?\"", meta_val)
        ],
        [
            Paragraph("<b>RAG & Hallucinations</b>", meta_val),
            Paragraph("\"Hey {first_name}, Alex here. Reaching out because many engineering teams are tackling LLM hallucinations and multi-agent coordination right now. Is custom AI systems development on your roadmap?\"", meta_val)
        ]
    ]
    hooks_tbl = Table(hooks_data, colWidths=[130, 410])
    hooks_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(hooks_tbl)
    
    story.append(PageBreak())
    
    # ---------------------------------------------------------
    # SECTION 5: ACTION & TOOL EXECUTION ENGINE
    # ---------------------------------------------------------
    story.append(Paragraph("5. Backend Action Execution Engine (7 Core System Actions)", section_heading))
    story.append(Paragraph(
        "The system executes seven deterministic actions in response to conversational states, webhook signals, and intent detection:",
        body_style
    ))
    story.append(Spacer(1, 6))
    
    actions_data = [
        [
            Paragraph("<b>Action Name</b>", meta_key),
            Paragraph("<b>Source File & Trigger</b>", meta_key),
            Paragraph("<b>Execution Logic & System Mutations</b>", meta_key)
        ],
        [
            Paragraph("<b>Action 1: Outbound Pacer Dispatch</b>", meta_val),
            Paragraph("run_humanoid_campaign_pacer.py<br/>Trigger: Lead stage='new_lead'", meta_val),
            Paragraph("Queries circuit breaker (<20/hr, <50/day). Checks 9:00-17:30 business window. Posts initial AI hook. Advances stage to 'attempted_contact', sub_status='outreach_sent'.", meta_val)
        ],
        [
            Paragraph("<b>Action 2: TCPA Suppression</b>", meta_val),
            Paragraph("ai-service/api/sms/router.py<br/>Trigger: STOP / UNSUBSCRIBE / Hostile", meta_val),
            Paragraph("Sets opted_out=TRUE, stage='dead', sub_status='compliance_opt_out'. Writes phone to permanent blacklist. Sends single-line carrier confirmation: 'You have been unsubscribed...'", meta_val)
        ],
        [
            Paragraph("<b>Action 3: Funky Wrong-Number Pivot</b>", meta_val),
            Paragraph("ai-service/api/sms/router.py<br/>Trigger: 'wrong number' / 'not Dave'", meta_val),
            Paragraph("Evaluates sentiment. If hostile, triggers Action 2. If confused/friendly, returns playful carrier pigeon pivot. Tags record as 'wrong_number_pivot'.", meta_val)
        ],
        [
            Paragraph("<b>Action 4: Appointment Detection</b>", meta_val),
            Paragraph("ai-service/api/sms/router.py<br/>Trigger: Lead accepts discovery call", meta_val),
            Paragraph("Executes background JSON-mode LLM call on last 8 messages. Returns {\"call_confirmed\": bool, \"time\": str, \"email\": str}. Guards against false positives.", meta_val)
        ],
        [
            Paragraph("<b>Action 5: Google Calendar & ICS</b>", meta_val),
            Paragraph("ai-service/core/gmail.py<br/>Trigger: Action 4 confirmed=true", meta_val),
            Paragraph("Converts relative time to UTC ISO-8601. Calls Google Calendar API events.insert with auto-generated Google Meet video room. Emails ICS calendar invitation.", meta_val)
        ],
        [
            Paragraph("<b>Action 6: Stage & Status Audit</b>", meta_val),
            Paragraph("crm-service/routers/leads.py<br/>Trigger: Stage lifecycle mutation", meta_val),
            Paragraph("Commits immutable audit record to `lead_status_history` table recording event, from_stage, to_stage, channel, and metadata.", meta_val)
        ],
        [
            Paragraph("<b>Action 7: Activity Feed SSE Emit</b>", meta_val),
            Paragraph("crm-service/routers/activity_feed.py<br/>Trigger: Any lead status change", meta_val),
            Paragraph("Broadcasts Server-Sent Event (SSE) over /api/activity-feed/stream. Next.js dashboard updates Kanban cards and displays notification toast.", meta_val)
        ]
    ]
    actions_tbl = Table(actions_data, colWidths=[120, 140, 280])
    actions_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(actions_tbl)
    story.append(Spacer(1, 10))
    
    # ---------------------------------------------------------
    # SECTION 6: STATE MACHINE & VERIFICATION
    # ---------------------------------------------------------
    story.append(Paragraph("6. Lead Lifecycle State Machine & Operational Commands", section_heading))
    
    state_data = [
        [
            Paragraph("<b>Stage</b>", meta_key),
            Paragraph("<b>Sub-Status</b>", meta_key),
            Paragraph("<b>Trigger Condition</b>", meta_key),
            Paragraph("<b>Automated Action</b>", meta_key)
        ],
        [
            Paragraph("<b>new_lead</b>", meta_val),
            Paragraph("new", meta_val),
            Paragraph("CSV Upload or API Ingest", meta_val),
            Paragraph("Enqueued for campaign pacer.", meta_val)
        ],
        [
            Paragraph("<b>attempted_contact</b>", meta_val),
            Paragraph("outreach_sent", meta_val),
            Paragraph("Pacer fires initial AI hook", meta_val),
            Paragraph("Message delivered; waiting for reply.", meta_val)
        ],
        [
            Paragraph("<b>engaged</b>", meta_val),
            Paragraph("replied", meta_val),
            Paragraph("Lead responds to text", meta_val),
            Paragraph("Active chat thread; AI enters Stage 1 diagnose.", meta_val)
        ],
        [
            Paragraph("<b>qualified</b>", meta_val),
            Paragraph("ai_diagnosed", meta_val),
            Paragraph("AI bottleneck scoped", meta_val),
            Paragraph("AI enters Stage 3; discovery call proposed.", meta_val)
        ],
        [
            Paragraph("<b>call_scheduled</b>", meta_val),
            Paragraph("appointment_confirmed", meta_val),
            Paragraph("Time & email confirmed", meta_val),
            Paragraph("Google Calendar invite created; meeting set.", meta_val)
        ],
        [
            Paragraph("<b>dead</b>", meta_val),
            Paragraph("compliance_opt_out", meta_val),
            Paragraph("STOP, unsubscribe, or decline", meta_val),
            Paragraph("DNC list updated; all pacing halted.", meta_val)
        ]
    ]
    state_tbl = Table(state_data, colWidths=[95, 105, 140, 200])
    state_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(state_tbl)
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Operational Verification Endpoints:", sub_heading))
    cmd_box = (
        "# 1. Health checks across running services:\n"
        "curl http://localhost:8003/health   # crm-service (200 OK)\n"
        "curl http://localhost:8002/health   # ai-service (200 OK)\n"
        "curl -I http://localhost:3001       # Next.js frontend (200 OK)\n\n"
        "# 2. Check campaign pacer & velocity safety limit:\n"
        "curl http://localhost:8002/api/sms/safety-status\n\n"
        "# 3. Run or test the campaign pacer daemon:\n"
        "./crm-service/venv/bin/python3 scripts/run_humanoid_campaign_pacer.py\n\n"
        "# 4. Refresh database persona prompt:\n"
        "./crm-service/venv/bin/python3 scripts/update_allzone_personality.py"
    )
    cmd_tbl = Table([[Paragraph(clean(cmd_box).replace('\n', '<br/>'), code_box_text)]], colWidths=[540])
    cmd_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_CODE),
        ('BOX', (0,0), (-1,-1), 1, TECH_BLUE),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(cmd_tbl)
    
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated architecture & prompts PDF: {output_filename}")

if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "/Users/ec2-user/troy-campaign/AllZone_AI_Lead_Funnel_Architecture_and_Prompts.pdf"
    build_pdf(out_path)
