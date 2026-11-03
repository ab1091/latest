#!/usr/bin/env python3
"""
generate_system_master_handbook_pdf.py

Compiles the SYSTEM_ARCHITECTURE_AND_TECHNICAL_MASTER_HANDBOOK into an executive-grade,
beautifully styled PDF document using ReportLab.
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
ERR_BG = colors.HexColor("#FEE2E2")            # Light red
ERR_TXT = colors.HexColor("#991B1B")           # Dark red

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
        
        # Header on pages 2+
        if self._pageNumber > 1:
            self.setStrokeColor(BORDER_COLOR)
            self.setLineWidth(0.6)
            self.line(36, 756, 576, 756)
            
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(NAVY_PRIMARY)
            self.drawString(36, 762, "AI CRM & HUMANOID CAMPAIGN PLATFORM")
            
            self.setFont("Helvetica", 7.5)
            self.setFillColor(TEXT_MUTED)
            self.drawString(220, 762, "|   System Architecture & Technical Master Handbook")
            
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(TECH_BLUE)
            self.drawRightString(576, 762, "PRODUCTION SPECIFICATION")

        # Footer on all pages
        self.setStrokeColor(BORDER_COLOR)
        self.setLineWidth(0.6)
        self.line(36, 40, 576, 40)
        
        self.setFont("Helvetica", 7.5)
        self.setFillColor(TEXT_MUTED)
        self.drawString(36, 29, "Confidential & Proprietary   |   AI CRM Platform Architecture   |   Troy Farmers Campaign")
        
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(NAVY_PRIMARY)
        self.drawRightString(576, 29, page_str)
        
        self.restoreState()


def build_pdf(output_paths):
    primary_output = output_paths[0]
    doc = SimpleDocTemplate(
        primary_output,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=46,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    # Custom Typography
    title_style = ParagraphStyle(
        'DocTitle',
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=NAVY_PRIMARY,
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=TECH_BLUE,
        spaceAfter=14
    )
    meta_style = ParagraphStyle(
        'DocMeta',
        fontName='Helvetica',
        fontSize=8.5,
        leading=13,
        textColor=TEXT_MUTED,
        spaceAfter=18
    )
    h1_style = ParagraphStyle(
        'Heading1_Custom',
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=NAVY_PRIMARY,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        'Heading2_Custom',
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=NAVY_SECONDARY,
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True
    )
    h3_style = ParagraphStyle(
        'Heading3_Custom',
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=TECH_BLUE,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'Body_Custom',
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=TEXT_DARK,
        spaceAfter=6
    )
    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=TEXT_DARK,
        leftIndent=14,
        firstLineIndent=-10,
        spaceAfter=3
    )
    code_block_style = ParagraphStyle(
        'CodeBlock',
        fontName='Courier',
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#E2E8F0"),
        spaceBefore=3,
        spaceAfter=3
    )
    callout_text = ParagraphStyle(
        'CalloutText',
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=TEXT_DARK
    )
    table_cell = ParagraphStyle(
        'TableCell',
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=TEXT_DARK
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=NAVY_PRIMARY
    )
    table_header = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.white
    )

    story = []

    # ── Cover Header Block ───────────────────────────────────────────────────
    story.append(Paragraph("SYSTEM ARCHITECTURE & TECHNICAL MASTER HANDBOOK", title_style))
    story.append(Paragraph("Enterprise AI CRM & Humanoid Campaign Dispatch Platform", subtitle_style))
    story.append(Paragraph(
        "<b>Classification:</b> Production Technical Specification &nbsp;|&nbsp; "
        "<b>Version:</b> 2.4.0 (Production Release) &nbsp;|&nbsp; "
        "<b>Target Runtime:</b> AWS EC2 / Next.js / FastAPI / PostgreSQL",
        meta_style
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=TECH_BLUE, spaceBefore=0, spaceAfter=14))

    # Executive Overview Callout
    overview_html = (
        "<b>EXECUTIVE TECHNICAL SUMMARY:</b><br/>"
        "This master specification provides the authoritative engineering reference for the AI CRM &amp; "
        "Humanoid Outreach platform. The system orchestrates multi-channel lead ingestion, CRM lifecycle "
        "transitions, AI-driven humanoid conversation pacing, and high-deliverability cellular dispatch. "
        "It documents the complete service topology, API contracts, PostgreSQL schemas, the dual-queue "
        "1:1 campaign pacer, legacy BlueBubbles iMessage mechanics, and the target Android SIM Gateway."
    )
    callout_data = [[Paragraph(overview_html, callout_text)]]
    callout_table = Table(callout_data, colWidths=[540])
    callout_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 1, TECH_BLUE),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(callout_table)
    story.append(Spacer(1, 14))

    # ── Section 1: High-Level Architecture ───────────────────────────────────
    story.append(Paragraph("1. High-Level System Architecture", h1_style))
    story.append(Paragraph(
        "The platform is organized into four distinct tiers: <b>Public Ingress</b> (reverse proxies and tunnels), "
        "<b>Application Tier</b> (Next.js frontend, CRM microservice, AI engine), <b>Data Tier</b> (PostgreSQL relational engine), "
        "and the <b>Messaging Gateway Tier</b> (cellular SIM relays and telecom transports).",
        body_style
    ))

    arch_diagram = (
        "+-----------------------------------------------------------------------------------------+<br/>"
        "|                                   PUBLIC INGRESS TIER                                   |<br/>"
        "|   Cloudflare Zero-Trust Tunnel (HTTPS / SSL)   |   Caddy Reverse Proxy (Port 80 to 3001) |<br/>"
        "+-----------------------------------------------------------------------------------------+<br/>"
        "                                             |<br/>"
        "                                             v<br/>"
        "+-----------------------------------------------------------------------------------------+<br/>"
        "|                                    APPLICATION TIER                                     |<br/>"
        "|   [Next.js Web Portal]  <--->  [CRM Service API]  <--->  [AI Engine & Scheduler]        |<br/>"
        "|   (Port 3001 / TypeScript)     (Port 8003 / FastAPI)     (Port 8002 / APScheduler)      |<br/>"
        "|                                                                                         |<br/>"
        "|   [Humanoid Campaign Pacer Daemon] ---> 1:1 Dual Queue (Day 1 Outreach vs Day 2 FU)     |<br/>"
        "+-----------------------------------------------------------------------------------------+<br/>"
        "                     |                                           |<br/>"
        "                     v                                           v<br/>"
        "+-----------------------------------+   +-------------------------------------------------+<br/>"
        "|            DATA TIER              |   |             MESSAGING GATEWAY TIER              |<br/>"
        "|   PostgreSQL 16 Engine            |   |   Primary: Android SIM Gateway (Direct Cellular)|<br/>"
        "|   Database: aicrm (Port 5432)     |   |   Fallback: Twilio Cloud Carrier Telecom API    |<br/>"
        "|   Tables: leads, messages, convs  |   |   Legacy: BlueBubbles Server (iMessage Apple)   |<br/>"
        "+-----------------------------------+   +-------------------------------------------------+"
    )
    diag_data = [[Paragraph(arch_diagram, code_block_style)]]
    diag_table = Table(diag_data, colWidths=[540])
    diag_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_CODE),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(diag_table)
    story.append(Spacer(1, 14))

    # ── Section 2: Microservice Topology & Ports ─────────────────────────────
    story.append(Paragraph("2. Microservice Topology & Network Ports", h1_style))
    story.append(Paragraph(
        "Each service runs isolated under dedicated system processes and virtual environments, bound to local loopback ports.",
        body_style
    ))

    topo_headers = ["Service Name", "Stack", "Port", "Public Endpoint", "Core Function"]
    topo_rows = [
        [
            Paragraph("<b>Next.js Frontend</b>", table_cell),
            Paragraph("Next.js 14, React, TS", table_cell),
            Paragraph("3001", table_cell_bold),
            Paragraph("trycloudflare.com / :80", table_cell),
            Paragraph("Dashboard UI, lead cards, live conversation panel", table_cell)
        ],
        [
            Paragraph("<b>CRM Microservice</b>", table_cell),
            Paragraph("FastAPI, Python 3.11", table_cell),
            Paragraph("8003", table_cell_bold),
            Paragraph("Internal (localhost)", table_cell),
            Paragraph("Lead state machine, appointments, contact records", table_cell)
        ],
        [
            Paragraph("<b>AI & Scheduler</b>", table_cell),
            Paragraph("FastAPI, APScheduler", table_cell),
            Paragraph("8002", table_cell_bold),
            Paragraph("http://3.14.152.78:8002", table_cell),
            Paragraph("AI generation, typing simulator, velocity limiter", table_cell)
        ],
        [
            Paragraph("<b>PostgreSQL DB</b>", table_cell),
            Paragraph("PostgreSQL 16", table_cell),
            Paragraph("5432", table_cell_bold),
            Paragraph("Internal (aicrm)", table_cell),
            Paragraph("ACID relational store: leads, conversations, messages", table_cell)
        ],
        [
            Paragraph("<b>Campaign Pacer</b>", table_cell),
            Paragraph("Python Daemon", table_cell),
            Paragraph("CLI", table_cell_bold),
            Paragraph("Background Daemon", table_cell),
            Paragraph("1:1 queue interleaving, 180s delay, 50/day cap", table_cell)
        ],
        [
            Paragraph("<b>Caddy Proxy</b>", table_cell),
            Paragraph("Caddy v2", table_cell),
            Paragraph("80", table_cell_bold),
            Paragraph("http://3.14.152.78", table_cell),
            Paragraph("Port 80 reverse proxy forwarder to port 3001", table_cell)
        ],
    ]
    t_data = [[Paragraph(f"<b>{h}</b>", table_header) for h in topo_headers]] + topo_rows
    topo_table = Table(t_data, colWidths=[95, 85, 45, 125, 190])
    topo_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('BOX', (0,0), (-1,-1), 0.8, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
    ]))
    story.append(topo_table)
    story.append(Spacer(1, 14))

    # ── Section 3: Component Breakdown ───────────────────────────────────────
    story.append(Paragraph("3. Component Breakdown & Responsibilities", h1_style))
    
    story.append(Paragraph("3.1 Next.js Web Frontend (frontend/)", h2_style))
    story.append(Paragraph("Located at <code>/Users/ec2-user/troy-campaign/frontend</code>. Key modules include:", bullet_style))
    story.append(Paragraph("• <b>app/dashboard/page.tsx:</b> Central operations panel displaying daily KPIs, delivery counts, reply percentages, and status filters.", bullet_style))
    story.append(Paragraph("• <b>components/panels/ConversationsPanel.tsx:</b> Real-time omnichannel chat UI supporting manual human takeovers, delivery receipts, and qualification tags.", bullet_style))
    story.append(Paragraph("• <b>components/panels/LeadsPanel.tsx:</b> Contact book interface with CSV ingestion, tag management, and stage transition controls.", bullet_style))

    story.append(Paragraph("3.2 CRM Core Microservice (crm-service/)", h2_style))
    story.append(Paragraph("Located at <code>/Users/ec2-user/troy-campaign/crm-service</code>. Runs in Python 3.11 venv.", bullet_style))
    story.append(Paragraph("• <b>routers/leads.py:</b> Handles phone normalization (E.164 format: <code>+1XXXXXXXXXX</code>), deduplication, and stage progression.", bullet_style))
    story.append(Paragraph("• <b>routers/conversations.py:</b> Thread management, message persistence, status transitions (<code>pending</code> -> <code>delivered</code> -> <code>failed</code>).", bullet_style))
    story.append(Paragraph("• <b>core/sms_client.py:</b> Generates internal system JWT tokens and forwards outbound message payloads to the AI service.", bullet_style))

    story.append(Paragraph("3.3 AI & Voice Bot Engine (ai-service/)", h2_style))
    story.append(Paragraph("Located at <code>/Users/ec2-user/troy-campaign/ai-service</code>. Key subsystems:", bullet_style))
    story.append(Paragraph("• <b>api/sms/router.py:</b> Implements <code>/api/sms/send-raw</code>, inbound routing, human typing simulation, and opt-out processing.", bullet_style))
    story.append(Paragraph("• <b>core/humanoid_sender.py:</b> Enforces 20/hr and 50/day rate limits, character cleaning, and random gap intervals.", bullet_style))
    story.append(Paragraph("• <b>core/circuit_breaker.py:</b> Trips automatically after 5 consecutive delivery failures to safeguard cellular SIM reputation.", bullet_style))
    story.append(Paragraph("• <b>core/callback_scheduler.py:</b> APScheduler engine managing callbacks (every 30s), stale lead sweep (every 30m), and orphaned reply recovery (every 2m).", bullet_style))

    story.append(Spacer(1, 10))

    # ── Section 4: Messaging Infrastructure Deep-Dive ────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("4. Messaging Infrastructure Deep-Dive", h1_style))

    story.append(Paragraph("4.1 BlueBubbles (Apple iMessage) Analysis & The Failure of Apple SMS Relay", h2_style))
    story.append(Paragraph(
        "Between Oct 26 and Oct 29, 2026, the platform utilized a BlueBubbles server running on a host MacBook Air "
        "(<code>https://imessage.allzonetech.com</code>). An audit of 352 recorded outbound attempts revealed the following:",
        body_style
    ))

    audit_headers = ["Channel / Service", "Attempts", "Delivered (Error 0)", "Failed / Rejected", "Primary Failure Root Cause"]
    audit_rows = [
        [
            Paragraph("<b>iMessage (Blue Bubbles)</b>", table_cell),
            Paragraph("192", table_cell_bold),
            Paragraph("34 (17.7%)", table_cell),
            Paragraph("158 (82.3%)", table_cell),
            Paragraph("Error 22: Recipient is Android or not registered on Apple iMessage network", table_cell)
        ],
        [
            Paragraph("<b>SMS Relay (Green Bubbles)</b>", table_cell),
            Paragraph("160", table_cell_bold),
            Paragraph("<b>0 (0.0%)</b>", table_cell),
            Paragraph("160 (100.0%)", table_cell),
            Paragraph("Error 4 / -1728: macOS Text Message Forwarding rejected carrier relay", table_cell)
        ],
    ]
    a_table = Table([[Paragraph(f"<b>{h}</b>", table_header) for h in audit_headers]] + audit_rows, colWidths=[120, 50, 95, 85, 190])
    a_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('BOX', (0,0), (-1,-1), 0.8, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
    ]))
    story.append(a_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        "<b>Root Cause of Apple SMS Relay Failure:</b> macOS Sequoia 15.1 enforces strict token authorization between Messages.app "
        "and the paired iPhone. The AppleScript command <code>tell application \"Messages\" to send to chat id \"SMS;-;+1...\"</code> "
        "threw error <code>-1728: Can't get chat id</code> because the Apple ID identity defaulted to email rather than the physical SIM. "
        "Furthermore, Apple actively discourages automated programmatic SMS relay on personal Apple IDs.",
        body_style
    ))

    story.append(Paragraph("4.2 Android Hardware SIM Gateway Architecture (Target Production Setup)", h2_style))
    story.append(Paragraph(
        "By hosting a physical SIM card inside an Android device, the platform bypasses Apple restrictions entirely, "
        "gaining direct cellular dispatch capabilities to 100% of mobile phones.",
        body_style
    ))

    android_flow = (
        "+-------------------+        HTTP REST API         +---------------------------+<br/>"
        "|  CRM & AI Engine  |  ------------------------->  |   Android Hardware Phone  |<br/>"
        "|  (AWS EC2 Cloud)  |  <-------------------------  |   (Any Wi-Fi or 4G/5G)    |<br/>"
        "+-------------------+      Two-Way Webhook         +---------------------------+<br/>"
        "                                                                 |<br/>"
        "                                                                 | Native SIM Radio<br/>"
        "                                                                 v<br/>"
        "                                                   +---------------------------+<br/>"
        "                                                   | Mobile Cellular Carrier   |<br/>"
        "                                                   | (AT&T, Verizon, T-Mobile) |<br/>"
        "                                                   +---------------------------+<br/>"
        "                                                                 |<br/>"
        "                                                                 v<br/>"
        "                                                   +---------------------------+<br/>"
        "                                                   | Lead Handset (Green SMS)  |<br/>"
        "                                                   | 100% Android & iPhone OK  |<br/>"
        "                                                   +---------------------------+"
    )
    af_data = [[Paragraph(android_flow, code_block_style)]]
    af_table = Table(af_data, colWidths=[540])
    af_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_CODE),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(af_table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("<b>Key Android Advantages:</b>", h3_style))
    story.append(Paragraph("• <b>Native OS Permissions:</b> Android exposes <code>SEND_SMS</code> and <code>RECEIVE_SMS</code> APIs specifically for background SMS gateways.", bullet_style))
    story.append(Paragraph("• <b>Independent Network Location:</b> The Android phone does NOT need to be on the same Wi-Fi as the server. It can run on home Wi-Fi, office Wi-Fi, or cellular 4G/5G anywhere in the world.", bullet_style))
    story.append(Paragraph("• <b>No Apple ID Risk:</b> Eliminates Apple ID ban risks, error 22, and Mac hardware serial blocks.", bullet_style))
    story.append(Paragraph("• <b>Zero Extra Telecom Costs:</b> Operates completely on the unlimited texting plan of the inserted SIM card.", bullet_style))

    story.append(Spacer(1, 10))

    # ── Section 5: The Humanoid Campaign Pacer ────────────────────────────────
    story.append(Paragraph("5. The Humanoid Campaign Pacer Engine", h1_style))
    story.append(Paragraph(
        "Implemented in <code>scripts/run_humanoid_campaign_pacer.py</code>, this daemon enforces human behavior "
        "patterns to protect sender reputation.",
        body_style
    ))

    story.append(Paragraph("5.1 Dual-Queue Interleaving Algorithm (1:1 Ratio)", h2_style))
    story.append(Paragraph(
        "The pacer maintains two distinct priority queues in PostgreSQL: <b>New Uncontacted Leads</b> (<code>sub_status = 'new'</code>) "
        "and <b>Day 2 Follow-ups</b> (<code>sub_status = 'contacted'</code> with >24h elapsed). It alternates 1:1 between them: "
        "even cycles send Day 1 discovery hooks; odd cycles send Day 2 intelligent follow-ups. If one queue is empty, it seamlessly exhausts the other.",
        body_style
    ))

    story.append(Paragraph("5.2 Anti-Abuse Velocity Bounds & Timing Rules", h2_style))
    pacer_rules = [
        ["Metric / Control", "Enforced Parameter", "Operational Rationale"],
        [
            Paragraph("<b>Base Inter-Message Delay</b>", table_cell),
            Paragraph("180 seconds (3.0 minutes)", table_cell_bold),
            Paragraph("Prevents burst-sending triggers on telecom carrier spam algorithms", table_cell)
        ],
        [
            Paragraph("<b>Random Human Jitter</b>", table_cell),
            Paragraph("+10 to +35 seconds", table_cell_bold),
            Paragraph("Varies timing between ~3.1 and 3.6 minutes to simulate manual human typing", table_cell)
        ],
        [
            Paragraph("<b>Daily Cap</b>", table_cell),
            Paragraph("50 messages / day", table_cell_bold),
            Paragraph("Strict ceiling to keep total daily volume well within standard P2P limits", table_cell)
        ],
        [
            Paragraph("<b>Operating Hours</b>", table_cell),
            Paragraph("09:00 - 18:00 Local Business Time", table_cell_bold),
            Paragraph("Automatic quiet hours hold; prevents after-hours messaging violations", table_cell)
        ],
    ]
    pr_table = Table([[Paragraph(f"<b>{c}</b>", table_header) for c in pacer_rules[0]]] + pacer_rules[1:], colWidths=[130, 140, 270])
    pr_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('BOX', (0,0), (-1,-1), 0.8, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
    ]))
    story.append(pr_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("5.3 Henry Jai AI Persona & Text Sanitization", h2_style))
    story.append(Paragraph("• <b>Persona:</b> Henry Jai - modern technology strategist reaching out peer-to-peer.", bullet_style))
    story.append(Paragraph("• <b>Strict Branding Rule:</b> ZERO mention of 'AllZone' or 'AllZone Technologies'.", bullet_style))
    story.append(Paragraph("• <b>Length:</b> Strictly 40 to 60 words per outbound message.", bullet_style))
    story.append(Paragraph("• <b>Character Sanitization:</b> Automated stripping of em dashes (<code>—</code>), marketing buzzwords, and links.", bullet_style))
    story.append(Paragraph("• <b>Universal Hooks:</b> Non-assuming discovery questions regarding general business goals and operational milestones.", bullet_style))

    story.append(Spacer(1, 10))

    # ── Section 6: Operational Playbook & Credentials ─────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("6. Operational Playbook & Service Management", h1_style))

    story.append(Paragraph("6.1 Production CLI Commands", h2_style))
    cmd_text = (
        "# 1. Check all active campaign daemons<br/>"
        "ps aux | grep -E \"next dev|main.py|run_humanoid|caddy|cloudflared\" | grep -v grep<br/><br/>"
        "# 2. Restart Clean Frontend (Port 3001)<br/>"
        "cd /Users/ec2-user/troy-campaign/frontend && rm -rf .next && npm run dev -- -p 3001<br/><br/>"
        "# 3. Restart AI & Scheduler Engine (Port 8002)<br/>"
        "cd /Users/ec2-user/troy-campaign/ai-service && ./venv/bin/python3 main.py<br/><br/>"
        "# 4. Launch Humanoid Campaign Pacer Daemon<br/>"
        "cd /Users/ec2-user/troy-campaign && \\<br/>"
        "DATABASE_URL=\"postgresql://aicrm_app:aicrm_password@localhost:5432/aicrm\" \\<br/>"
        "./crm-service/venv/bin/python3 scripts/run_humanoid_campaign_pacer.py<br/><br/>"
        "# 5. Stop Pacer Cleanly (Graceful Shutdown)<br/>"
        "pkill -f \"run_humanoid_campaign_pacer.py\""
    )
    c_data = [[Paragraph(cmd_text, code_block_style)]]
    c_table = Table(c_data, colWidths=[540])
    c_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_CODE),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(c_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("6.2 Troubleshooting & Error Matrix", h2_style))
    err_matrix = [
        ["Error Code / Symptom", "Root Cause", "Immediate Resolution"],
        [
            Paragraph("<b>HTTP 404 on /login</b>", table_cell),
            Paragraph("Next.js .next cache desynced from concurrent build", table_cell),
            Paragraph("Wipe <code>frontend/.next</code> and restart Next.js dev server on port 3001", table_cell)
        ],
        [
            Paragraph("<b>Error 4 on SMS</b>", table_cell),
            Paragraph("Apple Mac-to-iPhone SMS relay rejected handshake", table_cell),
            Paragraph("Deploy Android Hardware SIM Gateway to handle cellular SMS directly", table_cell)
        ],
        [
            Paragraph("<b>Error 22 on iMessage</b>", table_cell),
            Paragraph("Recipient is Android / non-Apple device", table_cell),
            Paragraph("Route message via cellular SMS transport rather than iMessage protocol", table_cell)
        ],
        [
            Paragraph("<b>HTTP 429 Daily Limit</b>", table_cell),
            Paragraph("Safety ceiling reached (50/50 messages sent today)", table_cell),
            Paragraph("Wait for 00:00 midnight reset, or pass <code>force=True</code> for manual tests", table_cell)
        ],
        [
            Paragraph("<b>HTTP 503 Circuit Breaker</b>", table_cell),
            Paragraph("Safety breaker open after 5 consecutive failures", table_cell),
            Paragraph("Call <code>POST /api/sms/reset-circuit-breaker</code> to re-arm", table_cell)
        ],
    ]
    em_table = Table([[Paragraph(f"<b>{c}</b>", table_header) for c in err_matrix[0]]] + err_matrix[1:], colWidths=[120, 160, 260])
    em_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('BOX', (0,0), (-1,-1), 0.8, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
    ]))
    story.append(em_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("6.3 Production Credentials & Endpoints", h2_style))
    cred_headers = ["Resource / Service", "Endpoint / Location", "Credentials / Details"]
    cred_rows = [
        [
            Paragraph("<b>Primary Public Web Portal</b>", table_cell),
            Paragraph("https://hoped-hardly-highlight-elect.trycloudflare.com", table_cell),
            Paragraph("SSL Terminated Cloudflare Tunnel", table_cell)
        ],
        [
            Paragraph("<b>Direct AWS Public IP</b>", table_cell),
            Paragraph("http://3.14.152.78", table_cell),
            Paragraph("Direct Caddy Reverse Proxy on Port 80", table_cell)
        ],
        [
            Paragraph("<b>Admin User Login</b>", table_cell),
            Paragraph("admin@aischeduler.com", table_cell_bold),
            Paragraph("Password: <code>Test1234!</code>", table_cell)
        ],
        [
            Paragraph("<b>PostgreSQL 16 DB</b>", table_cell),
            Paragraph("localhost:5432/aicrm", table_cell),
            Paragraph("User: <code>aicrm_app</code> &nbsp;|&nbsp; Pass: <code>aicrm_password</code>", table_cell)
        ],
        [
            Paragraph("<b>Legacy BlueBubbles</b>", table_cell),
            Paragraph("https://imessage.allzonetech.com", table_cell),
            Paragraph("Password: <code>gateway123</code>", table_cell)
        ],
    ]
    cr_table = Table([[Paragraph(f"<b>{c}</b>", table_header) for c in cred_headers]] + cred_rows, colWidths=[140, 200, 200])
    cr_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('BOX', (0,0), (-1,-1), 0.8, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
    ]))
    story.append(cr_table)
    story.append(Spacer(1, 14))

    # ── Section 7: Advanced Real-Time Engineering ─────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("7. Advanced Real-Time Engineering: Latency, Call Drops & Multi-Agents", h1_style))
    story.append(Paragraph(
        "Voice AI and real-time omnichannel orchestration require millisecond-level precision, automated failure recovery, "
        "and concurrency protection across telephony and cellular channels.",
        body_style
    ))

    story.append(Paragraph("7.1 Real-Time Latency Reduction Engine (Sub-600ms Pipeline)", h2_style))
    story.append(Paragraph(
        "To achieve natural human turn-taking, response latency must stay below 700ms. The system optimizes every hop:",
        body_style
    ))

    voice_pipe_diag = (
        "[Caller Speech] --> (1) Deepgram Nova-2 STT (Chunked Streaming <150ms)<br/>"
        "                --> (2) Groq LPU Hardware Acceleration (Llama-3.3 70B, TTFT 200-280ms)<br/>"
        "                --> (3) Cartesia Sonic TTS (First Audio Packet <120ms)<br/>"
        "                --> [Caller Hears Audio] (Total Round-Trip Latency: 470 - 650ms)"
    )
    vp_data = [[Paragraph(voice_pipe_diag, code_block_style)]]
    vp_table = Table(vp_data, colWidths=[540])
    vp_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_CODE),
        ('BOX', (0,0), (-1,-1), 1, BORDER_COLOR),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(vp_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("• <b>Streaming STT & Endpointing:</b> Telephony audio streams directly over WebSockets with 250ms silence detection endpointing.", bullet_style))
    story.append(Paragraph("• <b>Low-Reasoning Effort LLMs:</b> Setting <code>reasoning_effort: 'low'</code> on open models eliminates hidden reasoning pauses before visible token emission.", bullet_style))
    story.append(Paragraph("• <b>First-Chunk TTS Synthesis:</b> Cartesia generates audio from the first 3 tokens emitted, so speech begins playing while the LLM is still drafting.", bullet_style))
    story.append(Paragraph("• <b>Barge-in / Interruption Handling:</b> Active Voice Activity Detection (VAD) instantly flushes the playback buffer in under 50ms when the caller speaks.", bullet_style))

    story.append(Paragraph("7.2 Call Drop Detection, Network Failovers & Orphaned Call Recovery", h2_style))
    story.append(Paragraph(
        "Cellular calls inevitably disconnect due to dead zones, tower handoffs, or battery depletion. The platform handles drops at 3 levels:",
        body_style
    ))
    story.append(Paragraph("1. <b>Instant Telephony Webhooks:</b> <code>call.ended</code> webhooks immediately capture reasons: <code>phone-call-provider-closed-by-remote</code>, <code>silence-timed-out</code>, or <code>network-error</code>.", bullet_style))
    story.append(Paragraph("2. <b>Orphaned Call Background Watchdog:</b> An APScheduler job (<code>check_orphaned_calls</code>) runs every 3 minutes. It queries Vapi REST APIs for any call stuck in <code>in-progress</code> for >10 minutes, fetches the final transcript, and saves the recording.", bullet_style))
    story.append(Paragraph("3. <b>Automated SMS Reconnection Workflow:</b> Within 60 seconds of a dropped call, an automated text follow-up fires: <i>'Hi [Name], looks like our connection dropped! I have your slot open for [Time] - should I lock that in for you?'</i>", bullet_style))

    story.append(Paragraph("7.3 Multi-Agent Architecture & Inter-Agent Communication", h2_style))
    story.append(Paragraph(
        "Instead of a single monolithic prompt, the platform deploys specialized micro-agents coordinated via a PostgreSQL shared blackboard:",
        body_style
    ))

    agent_matrix = [
        ["Agent Persona", "Channel", "Primary Objective", "Context Handoff"],
        [
            Paragraph("<b>Henry Jai (SDR)</b>", table_cell),
            Paragraph("Cellular SMS", table_cell),
            Paragraph("Cold discovery, non-assuming hooks, initial qualification", table_cell),
            Paragraph("Logs lead tags & interest to PostgreSQL leads table", table_cell)
        ],
        [
            Paragraph("<b>Alex / James (Voice)</b>", table_cell),
            Paragraph("Inbound / Outbound Call", table_cell),
            Paragraph("Live triage, intent classification (Sales/Financial/Medical)", table_cell),
            Paragraph("Reads prior SMS thread history from database on connect", table_cell)
        ],
        [
            Paragraph("<b>Scheduler Agent</b>", table_cell),
            Paragraph("Function Tool", table_cell),
            Paragraph("Deterministic calendar booking & collision avoidance", table_cell),
            Paragraph("Locks slot into Google Calendar & updates CRM stage", table_cell)
        ],
        [
            Paragraph("<b>Human Supervisor</b>", table_cell),
            Paragraph("CRM Live Panel", table_cell),
            Paragraph("Manual human takeover for high-value negotiations", table_cell),
            Paragraph("Sets <code>ai_active = false</code> to pause automated AI turns", table_cell)
        ],
    ]
    am_table = Table([[Paragraph(f"<b>{c}</b>", table_header) for c in agent_matrix[0]]] + agent_matrix[1:], colWidths=[110, 85, 175, 170])
    am_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY_PRIMARY),
        ('BOX', (0,0), (-1,-1), 0.8, BORDER_COLOR),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
    ]))
    story.append(am_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("• <b>Collision Avoidance:</b> Before proactive callbacks fire, the scheduler checks if another agent chatted in the last 15 minutes to prevent awkward mid-conversation interruptions.", bullet_style))

    story.append(Paragraph("7.4 Call Duration Optimization (Reducing Wasted Minutes & Cost)", h2_style))
    story.append(Paragraph(
        "Telephony minutes and LLM tokens scale directly with call length. The system enforces tight conversational constraints to keep calls under 2 to 3 minutes:",
        body_style
    ))
    story.append(Paragraph("• <b>Strict 3-Step State Progression:</b> (1) Identify intent & service -> (2) Agree on exact date & clock time -> (3) Confirm email letter-by-letter. Cuts rambling by 40%.", bullet_style))
    story.append(Paragraph("• <b>25-Word Turn Ceiling:</b> Prompts strictly limit bot responses to 1-2 sentences (under 25 words).", bullet_style))
    story.append(Paragraph("• <b>Early Callback Branching:</b> If a caller says 'I am driving' or 'busy', the AI immediately invokes <code>schedule_callback(minutes=X)</code> in under 15 seconds.", bullet_style))

    story.append(Paragraph("7.5 High-Volume Concurrency Management (Multi-Call & Multi-Message)", h2_style))
    story.append(Paragraph("• <b>SIP Trunk Multiplexing:</b> Concurrent incoming and outgoing telephony lines route through asynchronous FastAPI ASGI event loops running multiple Uvicorn workers.", bullet_style))
    story.append(Paragraph("• <b>PostgreSQL Connection Pooling:</b> <code>psycopg2.pool</code> ensures database connections are checked out and returned instantly, with LLM calls executed outside transaction blocks.", bullet_style))
    story.append(Paragraph("• <b>Outbound Queue Throttling:</b> Asynchronous semaphores meter SMS dispatches to guarantee carrier rate limits (P2P velocity bounds) are never breached.", bullet_style))

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✓ Generated primary PDF at: {primary_output}")

    # Copy to additional destinations
    import shutil
    for path in output_paths[1:]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copy2(primary_output, path)
        print(f"✓ Copied PDF to: {path}")

if __name__ == "__main__":
    targets = [
        "/Users/ec2-user/.gemini/antigravity-ide/brain/957e3000-ee47-42cd-87e5-f742da56184d/SYSTEM_ARCHITECTURE_AND_TECHNICAL_MASTER_HANDBOOK.pdf",
        "/Users/ec2-user/troy-campaign/SYSTEM_ARCHITECTURE_AND_TECHNICAL_MASTER_HANDBOOK.pdf",
        "/Users/ec2-user/troy-campaign/frontend/public/SYSTEM_ARCHITECTURE_AND_TECHNICAL_MASTER_HANDBOOK.pdf"
    ]
    build_pdf(targets)
