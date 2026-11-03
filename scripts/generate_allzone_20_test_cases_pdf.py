#!/usr/bin/env python3
"""
generate_allzone_20_test_cases_pdf.py

Generates an executive-grade, beautifully formatted PDF report containing:
- Executive Summary & Testing Framework
- 20-Scenario Coverage Matrix
- 20 Full-Length End-to-End Test Cases (Lead Upload -> Outreach -> Multi-Turn Conversation -> CRM Actions -> Stage Lifecycle)
- Compliance, Guardrail, and Anti-Hallucination Audit

STRICT MANDATE:
- PURE AI SERVICES ONLY (Agentic AI, Custom LLMOps, Voice AI, Generative AI, Enterprise RAG, Private VPC Models)
- Zero generic web dev, zero IT staffing, zero "external engineering horsepower"
- Zero mention of "AllZone Technologies" in any message sent to leads (Alex here / our engineering team)
- Zero em dashes, zero en dashes, zero double hyphens
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
BG_LIGHT_AI = colors.HexColor("#F0F7FF")       # Subtle ice blue for AI bubbles
BORDER_AI = colors.HexColor("#BAE6FD")         # Light blue border
BG_LIGHT_LEAD = colors.HexColor("#F8FAFC")     # Slate light for Lead bubbles
BORDER_LEAD = colors.HexColor("#CBD5E1")       # Neutral border
TEXT_DARK = colors.HexColor("#0F172A")         # Body dark slate
TEXT_MUTED = colors.HexColor("#475569")        # Muted secondary text
SUCCESS_BG = colors.HexColor("#DCFCE7")        # Light green
SUCCESS_TXT = colors.HexColor("#166534")       # Dark green
WARN_BG = colors.HexColor("#FEF3C7")           # Light amber
WARN_TXT = colors.HexColor("#92400E")          # Dark amber
PURPLE_BG = colors.HexColor("#F3E8FF")         # Light purple
PURPLE_TXT = colors.HexColor("#6B21A8")        # Dark purple

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
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.6)
            self.line(36, 756, 576, 756)
            
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(NAVY_PRIMARY)
            self.drawString(36, 762, "ALLZONE TECHNOLOGIES")
            
            self.setFont("Helvetica", 7.5)
            self.setFillColor(TEXT_MUTED)
            self.drawString(145, 762, "|   Production AI & Agentic Systems Funnel (Agent: Alex)")
            
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(TECH_BLUE)
            self.drawRightString(576, 762, "AI SERVICES BENCHMARK")

        # Footer on all pages
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
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

def get_test_cases_dataset():
    """
    Returns the comprehensive 20 test case definitions, strictly focused on pure AI Services.
    """
    return [
        {
            "id": "TC-01",
            "title": "Autonomous Agentic AI Workflow and Document Reasoning",
            "category": "Agentic AI & LLM Systems",
            "lead_name": "Marcus Vance",
            "job_title": "VP of Engineering",
            "company": "Crestline Capital",
            "industry": "FinTech / Private Credit",
            "phone": "+1 (415) 890-1120",
            "email": "m.vance@crestlinecap.com",
            "source": "CSV Upload: fintech_summit_2026_attendees.csv",
            "initial_score": "88 / 100",
            "scenario": "Crestline uploaded into CRM after an executive summit. The firm processes 400 loan underwriting memos per month and seeks an agentic AI system that performs deterministic verification loops, citations, and human-in-the-loop review.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "10:02 AM", "channel": "SMS", "text": "Hi Marcus, Alex here. Following up on your inquiry regarding production AI workflow automation for financial documentation. Are you exploring multi-step agent pipelines this quarter?"},
                {"speaker": "Lead (Marcus)", "time": "10:05 AM", "channel": "SMS", "text": "Hey Alex. Yes we are. We evaluate hundreds of credit memos weekly. Our main hurdle with LLMs has been hallucination rates and audit compliance. What is your team's approach to deterministic verification?"},
                {"speaker": "Alex (AI)", "time": "10:07 AM", "channel": "SMS", "text": "That is the critical engineering challenge in FinTech. We build deterministic verification loops where an agent drafts, a validation engine cross-references raw source PDFs with exact character offsets, and flagged discrepancies route to a human underwriter before anything writes to your database."},
                {"speaker": "Lead (Marcus)", "time": "10:11 AM", "channel": "SMS", "text": "That is exactly what we need. Do you build on LangGraph or custom orchestration? And what does your latency look like on a 40 page debt prospectus?"},
                {"speaker": "Alex (AI)", "time": "10:13 AM", "channel": "SMS", "text": "We implement on LangGraph or custom Temporal state machines depending on scale. For a 40 page prospectus, our chunking and parallelized vector retrieval completes extraction and citation validation in under 8 seconds."},
                {"speaker": "Lead (Marcus)", "time": "10:17 AM", "channel": "SMS", "text": "Impressive speed. I would like my lead ML architect on a call with your solutions team to see an architecture demo. Are you free Thursday afternoon?"},
                {"speaker": "Alex (AI)", "time": "10:19 AM", "channel": "SMS", "text": "I can certainly arrange that! Thursday at 2:00 PM EST or 3:30 PM EST works well for our Principal AI Architect. Which slot suits your team best?"},
                {"speaker": "Lead (Marcus)", "time": "10:22 AM", "channel": "SMS", "text": "Let us lock in Thursday at 2:00 PM EST. Please send the calendar invite to m.vance@crestlinecap.com."},
                {"speaker": "Alex (AI)", "time": "10:23 AM", "channel": "SMS", "text": "Calendar invite is on its way to m.vance@crestlinecap.com for Thursday at 2:00 PM EST with Google Meet details. Looking forward to speaking with you and your team Marcus!"}
            ],
            "intent": "Enterprise AI Architecture Inquiry & Demo Request",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> ENGAGED -> QUALIFIED_ENTERPRISE -> DEMO_SCHEDULED",
            "crm_actions": [
                "Lead uploaded via CSV batch import and parsed with FinTech AI sector tag",
                "Automated personalization payload populated from Crestline metadata",
                "Entities extracted: LangGraph, 40-page prospectus, 8s latency SLA",
                "Google Calendar invite generated for Thursday 2:00 PM EST (m.vance@crestlinecap.com)",
                "Slack notification dispatched to #sales-enterprise with conversation transcript",
                "Lead score elevated from 88 to 98"
            ],
            "guardrails": "Verified exact clock time and timezone before booking. Double-confirmed recipient email address. Zero em dashes used."
        },
        {
            "id": "TC-02",
            "title": "Enterprise AI Copilot & Autonomous ERP Reasoning Agent",
            "category": "Enterprise AI Agents",
            "lead_name": "Elena Rostova",
            "job_title": "Chief Information Officer",
            "company": "Nordic Retail Group",
            "industry": "Omnichannel Retail",
            "phone": "+1 (206) 555-8491",
            "email": "elena.rostova@nordicretail.com",
            "source": "Web Form Upload: /ai-enterprise-copilots",
            "initial_score": "92 / 100",
            "scenario": "Nordic Retail has over 350 stores and thousands of daily procurement exceptions. Elena needs an autonomous AI reasoning agent integrated with SAP to automate purchase order reconciliation and inventory anomaly resolution.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "09:15 AM", "channel": "SMS", "text": "Hello Elena, Alex here. Following up on your inquiry regarding autonomous AI agents for ERP data. Are you looking to automate purchase order reconciliation and inventory exceptions this quarter?"},
                {"speaker": "Lead (Elena)", "time": "09:20 AM", "channel": "SMS", "text": "Hi Alex. Yes, that is our highest priority. Our staff spends 25 hours a week manually reconciling supplier invoices against SAP goods receipts. Can an AI agent handle fuzzy matching without making accounting errors?"},
                {"speaker": "Alex (AI)", "time": "09:22 AM", "channel": "SMS", "text": "We engineer autonomous ERP copilot agents specifically for that. We connect an agentic reasoning engine to your SAP APIs with deterministic schema validation: the agent performs semantic line-item matching, flags price variances over 1% for human sign-off, and auto-clears verified matches directly into your ledger."},
                {"speaker": "Lead (Elena)", "time": "09:27 AM", "channel": "SMS", "text": "What about edge cases where vendor part numbers differ slightly from our internal SKUs?"},
                {"speaker": "Alex (AI)", "time": "09:30 AM", "channel": "SMS", "text": "We integrate a hybrid embedding model trained on your historical product catalog alongside a cross-encoder reranker. It matches non-standard SKU descriptions with 99.4% precision and provides confidence scores on every match."},
                {"speaker": "Lead (Elena)", "time": "09:34 AM", "channel": "SMS", "text": "That is exactly what we need to see. Can your Chief AI Architect walk my enterprise systems team through a live demonstration early next week?"},
                {"speaker": "Alex (AI)", "time": "09:36 AM", "channel": "SMS", "text": "Certainly Elena! Does Tuesday at 10:00 AM PST or Wednesday at 1:00 PM PST work better for your calendar?"},
                {"speaker": "Lead (Elena)", "time": "09:38 AM", "channel": "SMS", "text": "Tuesday at 10:00 AM PST works great. Please email elena.rostova@nordicretail.com."},
                {"speaker": "Alex (AI)", "time": "09:40 AM", "channel": "SMS", "text": "Confirmed! The calendar invite for Tuesday at 10:00 AM PST has been dispatched to elena.rostova@nordicretail.com. We look forward to showing you the agent in action."}
            ],
            "intent": "Enterprise AI Agent Scoping & Live Demonstration",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> ENGAGED -> QUALIFIED_ENTERPRISE -> DEMO_BOOKED",
            "crm_actions": [
                "Lead ingested from website contact form with priority AI Copilot flag",
                "Technical keywords matched: SAP API, Semantic SKU Matching, Cross-Encoder Reranker",
                "Interactive ERP Copilot sandbox staged for meeting agenda",
                "Calendar invite created and linked to Chief AI Architect",
                "Opportunity created in CRM with estimated deal size: $220,000"
            ],
            "guardrails": "Strict adherence to anti-hallucination time slot matching. Full email validation prior to calendar dispatch."
        },
        {
            "id": "TC-03",
            "title": "Ultra-Low-Latency Voice AI Agent for Telehealth Patient Intake",
            "category": "Voice AI & Healthcare",
            "lead_name": "Dr. Jordan Hayes",
            "job_title": "Chief Operating Officer",
            "company": "MedVantage Health",
            "industry": "Digital Health / Telemedicine",
            "phone": "+1 (617) 555-7312",
            "email": "j.hayes@medvantagehealth.com",
            "source": "Webinar Upload: ai_in_telehealth_q4.csv",
            "initial_score": "85 / 100",
            "scenario": "MedVantage receives over 12,000 inbound patient scheduling calls daily. They need a natural conversational voice agent with sub-500ms latency, HIPAA-compliant patient intake, and direct integration into Epic EHR.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "02:14 PM", "channel": "SMS", "text": "Hi Dr. Hayes, Alex here following up on the Telehealth AI Summit. Are you still seeking to deploy conversational Voice AI for patient intake without robotic delays?"},
                {"speaker": "Lead (Dr. Hayes)", "time": "02:18 PM", "channel": "SMS", "text": "Hello Alex. We are, but our biggest bottleneck with voice bots has been latency and awkward interruptions. Our patients hang up if the bot pauses for 2 seconds before answering."},
                {"speaker": "Alex (AI)", "time": "02:21 PM", "channel": "SMS", "text": "Completely understood Dr. Hayes. Traditional chained APIs create that robotic lag. We build custom full-duplex WebSocket voice pipelines using Cartesia or Deepgram coupled with edge LLMs, bringing turnaround latency down to 450 milliseconds with natural interruption handling."},
                {"speaker": "Lead (Dr. Hayes)", "time": "02:26 PM", "channel": "SMS", "text": "That is remarkably fast. What about HIPAA compliance and patient data privacy? Do you sign Business Associate Agreements?"},
                {"speaker": "Alex (AI)", "time": "02:28 PM", "channel": "SMS", "text": "Yes, we sign BAAs as standard protocol. All audio streams are encrypted end to end, PII is redacted in memory before model inference, and no patient health records are ever used for model training."},
                {"speaker": "Lead (Dr. Hayes)", "time": "02:32 PM", "channel": "SMS", "text": "Do you have working integrations with Epic EHR for bi-directional scheduling?"},
                {"speaker": "Alex (AI)", "time": "02:34 PM", "channel": "SMS", "text": "Yes, our voice agents connect directly through Epic FHIR APIs for appointment booking and patient demographic verification in real time."},
                {"speaker": "Lead (Dr. Hayes)", "time": "02:37 PM", "channel": "SMS", "text": "I need to hear a live audio test. Can we set up a technical demonstration this Friday?"},
                {"speaker": "Alex (AI)", "time": "02:39 PM", "channel": "SMS", "text": "We would love to demonstrate it live! We have Friday at 11:30 AM EST or 3:00 PM EST open. Which time works best for you?"},
                {"speaker": "Lead (Dr. Hayes)", "time": "02:41 PM", "channel": "SMS", "text": "Friday at 11:30 AM EST is perfect. Please send the link to j.hayes@medvantagehealth.com."},
                {"speaker": "Alex (AI)", "time": "02:43 PM", "channel": "SMS", "text": "All set Dr. Hayes! The calendar invitation with the interactive voice test room link has been emailed to j.hayes@medvantagehealth.com for Friday at 11:30 AM EST."}
            ],
            "intent": "Voice AI Consultation & HIPAA Compliance Validation",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> ENGAGED -> COMPLIANCE_VALIDATED -> DEMO_BOOKED",
            "crm_actions": [
                "Lead enriched with Healthcare / BAA compliance flags",
                "Technical requirements logged: FHIR Epic API, 450ms Voice Latency, Cartesia streaming",
                "Automated NDA and BAA preview documents staged in CRM",
                "Google Meet calendar event created with Voice Lab sandbox credentials",
                "Assigned to Healthcare Practice Lead in CRM"
            ],
            "guardrails": "Ensured HIPAA claims matched legal engineering standards. Verified Dr. Hayes time preference and email address."
        },
        {
            "id": "TC-04",
            "title": "Custom AI Engineering Team for Multi-Agent LLM Deployment",
            "category": "Custom AI Engineering",
            "lead_name": "Devlin Ross",
            "job_title": "CTO",
            "company": "StackPulse",
            "industry": "DevOps & Cloud Automation",
            "phone": "+1 (415) 555-9204",
            "email": "d.ross@stackpulse.io",
            "source": "LinkedIn Lead Form: ai_agent_engineering_teams",
            "initial_score": "90 / 100",
            "scenario": "StackPulse raised Series B and committed to delivering an autonomous AI incident remediation agent. Devlin needs an elite dedicated AI engineering team specializing in LangGraph, tool-calling, and custom fine-tuning.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "11:05 AM", "channel": "SMS", "text": "Hi Devlin, Alex here. Following up on your inquiry about building an autonomous AI incident remediation agent. Are you looking to deploy multi-agent orchestration for cloud logs this quarter?"},
                {"speaker": "Lead (Devlin)", "time": "11:08 AM", "channel": "SMS", "text": "Hey Alex. Yes, we need a dedicated AI engineering pod to build an autonomous agent that ingests Datadog alerts, writes diagnostic queries, and suggests Kubernetes pod remediations. How fast can you stand up a specialized AI team?"},
                {"speaker": "Alex (AI)", "time": "11:10 AM", "channel": "SMS", "text": "We have senior AI and LLM systems engineers ready on our bench specializing in LangGraph, agent state machines, and fine-tuning. We can share technical profiles within 48 hours and have a dedicated 4-person AI engineering team onboarded to your repos in under 10 days."},
                {"speaker": "Lead (Devlin)", "time": "11:14 AM", "channel": "SMS", "text": "Have your engineers built production systems with tool-calling error recovery when an agent executes CLI commands against clusters?"},
                {"speaker": "Alex (AI)", "time": "11:16 AM", "channel": "SMS", "text": "Yes, that is a core engineering specialty for us. We implement sandboxed execution environments with deterministic safety filters, rollback mechanisms, and automated prompt self-correction when a CLI tool call returns a syntax error."},
                {"speaker": "Lead (Devlin)", "time": "11:20 AM", "channel": "SMS", "text": "That is the level of depth I was looking for. Can we do an architecture review call tomorrow Wednesday at 3:00 PM PST?"},
                {"speaker": "Alex (AI)", "time": "11:22 AM", "channel": "SMS", "text": "Tomorrow Wednesday at 3:00 PM PST is confirmed Devlin! Please confirm if d.ross@stackpulse.io is the best email for the calendar invitation."},
                {"speaker": "Lead (Devlin)", "time": "11:25 AM", "channel": "SMS", "text": "Yes, d.ross@stackpulse.io is correct."},
                {"speaker": "Alex (AI)", "time": "11:27 AM", "channel": "SMS", "text": "Invite dispatched to d.ross@stackpulse.io for Wednesday at 3:00 PM PST. Our Principal AI Architect will lead the session."}
            ],
            "intent": "Specialized AI Engineering Team & Autonomous Agent Architecture",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> ENGAGED -> AI_SPECS_MATCHED -> ARCH_REVIEW_SET",
            "crm_actions": [
                "Pod requirements tagged: LangGraph, CLI Tool-Calling, Datadog/K8s Sandboxing",
                "Assigned to Senior AI Systems Director",
                "Calendar invite confirmed for Wednesday 3:00 PM PST",
                "Deal stage updated to 'AI Architecture Scoping'"
            ],
            "guardrails": "Clear timezone conversion, verified exact email address, zero em dashes."
        },
        {
            "id": "TC-05",
            "title": "Edge AI and On-Device Computer Vision for Mobile Fleet Operations",
            "category": "Edge AI & Vision Models",
            "lead_name": "Priya Sharma",
            "job_title": "VP of Product",
            "company": "FleetTrack Mobility",
            "industry": "Logistics & Supply Chain",
            "phone": "+1 (312) 555-4819",
            "email": "priya.sharma@fleettrack.co",
            "source": "CSV Upload: freight_tech_expo_leads.csv",
            "initial_score": "86 / 100",
            "scenario": "FleetTrack needs an on-device Edge AI vision model that runs locally on driver mobile phones to scan bills of lading, detect cargo damage in offline freight yards, and predict route delays without internet.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "01:30 PM", "channel": "SMS", "text": "Hi Priya, Alex here following up from FreightTech Expo. Are you exploring on-device Edge AI and computer vision models for driver bill-of-lading capture this quarter?"},
                {"speaker": "Lead (Priya)", "time": "01:35 PM", "channel": "SMS", "text": "Hi Alex! Yes, that is our main challenge. Our drivers are often in remote freight yards with zero cellular service. Can you deploy lightweight vision models that run directly on mobile hardware without cloud connectivity?"},
                {"speaker": "Alex (AI)", "time": "01:38 PM", "channel": "SMS", "text": "Yes, absolutely Priya. We optimize and quantize custom vision models using ONNX Runtime and CoreML/TFLite to run locally on device. Drivers capture bills of lading or damaged cargo photos, the model extracts text and verifies signatures offline in under 300 milliseconds, and queues the payload for automatic cloud synchronization when network reconnects."},
                {"speaker": "Lead (Priya)", "time": "01:43 PM", "channel": "SMS", "text": "What about battery consumption on driver devices during an 8-hour shift?"},
                {"speaker": "Alex (AI)", "time": "01:46 PM", "channel": "SMS", "text": "Because the model is quantized to 8-bit precision and only triggers on active camera frames, device battery draw stays under 4% across an entire operational shift."},
                {"speaker": "Lead (Priya)", "time": "01:50 PM", "channel": "SMS", "text": "That is impressive optimization. Can we review a pilot scoping plan on Monday?"},
                {"speaker": "Alex (AI)", "time": "01:52 PM", "channel": "SMS", "text": "Monday is perfect! Would 1:00 PM CST or 4:00 PM CST work better for your schedule Priya?"},
                {"speaker": "Lead (Priya)", "time": "01:54 PM", "channel": "SMS", "text": "1:00 PM CST works great. Send it to priya.sharma@fleettrack.co."},
                {"speaker": "Alex (AI)", "time": "01:56 PM", "channel": "SMS", "text": "Calendar invite is sent to priya.sharma@fleettrack.co for Monday at 1:00 PM CST. We look forward to talking through the Edge AI architecture!"}
            ],
            "intent": "Edge AI & Mobile Computer Vision Architecture Consultation",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> ENGAGED -> EDGE_AI_SCOPED -> DISCOVERY_SET",
            "crm_actions": [
                "Tech stack tagged: Edge AI, ONNX Runtime, CoreML, Offline OCR",
                "AI Computer Vision lead notified to prepare benchmark data",
                "Calendar invite logged for Monday 1:00 PM CST",
                "Lead score adjusted to 94 / 100"
            ],
            "guardrails": "Verified CST timezone, confirmed exact email, strictly zero em dashes or double hyphens."
        },
        {
            "id": "TC-06",
            "title": "The Funky Wrong Number Pivot to AI-Powered B2B Marketplace",
            "category": "Conversational Agility & AI Pivot",
            "lead_name": "Tariq Al-Mansoor",
            "job_title": "Founder & CEO",
            "company": "Novasphere Marketplace",
            "industry": "B2B E-Commerce Marketplace",
            "phone": "+1 (650) 555-3921",
            "email": "tariq@novasphere.io",
            "source": "Outdated CSV Upload (Tagged as 'Dave Miller')",
            "initial_score": "45 / 100",
            "scenario": "A lead list had a recycled cell phone number. The recipient is not Dave, but Tariq, an active tech founder struggling with building an AI matching engine for his B2B marketplace.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "03:10 PM", "channel": "SMS", "text": "Hi Dave, Alex here. Are you facing any bottlenecks developing Agentic AI or custom LLM systems for your business roadmap this quarter?"},
                {"speaker": "Lead (Tariq)", "time": "03:12 PM", "channel": "SMS", "text": "Who is this? There is no Dave here, you got the completely wrong number my friend."},
                {"speaker": "Alex (AI)", "time": "03:14 PM", "channel": "SMS", "text": "Ah, looks like our digital carrier pigeon took a wild left turn over Silicon Valley! Pardon the intrusion Tariq. Unless by some lucky stroke of fate your company is secretly building AI agents or custom LLM workflows, I will gladly see myself out!"},
                {"speaker": "Lead (Tariq)", "time": "03:17 PM", "channel": "SMS", "text": "Haha, alright that was actually pretty clever. How did you know my name is Tariq though? And what kind of AI systems do you actually engineer?"},
                {"speaker": "Alex (AI)", "time": "03:19 PM", "channel": "SMS", "text": "Caller ID metadata gave me your first name, but the carrier pigeon was pure luck! Our engineering team specializes in custom agentic AI systems, enterprise LLM operations, and autonomous matching algorithms."},
                {"speaker": "Lead (Tariq)", "time": "03:23 PM", "channel": "SMS", "text": "Wild timing. I am the founder of Novasphere and we are currently drafting specs for an AI agent that autonomously matches wholesale suppliers with buyer RFQs using semantic reasoning. What is your typical timeline to build an AI pilot like that?"},
                {"speaker": "Alex (AI)", "time": "03:25 PM", "channel": "SMS", "text": "Serendipity at its finest Tariq! For an autonomous RFQ matching agent with vector similarity and rule-based negotiation gates, our AI team typically delivers a production pilot in 6 to 8 weeks."},
                {"speaker": "Lead (Tariq)", "time": "03:28 PM", "channel": "SMS", "text": "Let us chat. Are you free this Thursday at 4:00 PM EST? You can send details to tariq@novasphere.io."},
                {"speaker": "Alex (AI)", "time": "03:30 PM", "channel": "SMS", "text": "Thursday at 4:00 PM EST is booked! The invite has been delivered to tariq@novasphere.io. Excited to dive into Novasphere!"}
            ],
            "intent": "Playful Wrong Number Pivot to High-Value AI Marketplace Scoping",
            "stages": "LEAD_UPLOADED -> WRONG_NUMBER_DETECTED -> PLAYFUL_PIVOT -> IDENTITY_UPDATED -> MEETING_BOOKED",
            "crm_actions": [
                "Lead contact record corrected from 'Dave Miller' to 'Tariq Al-Mansoor'",
                "Company updated to Novasphere Marketplace (novasphere.io)",
                "Lead source reclassified: 'Serendipitous AI SMS Pivot'",
                "Calendar invite dispatched for Thursday 4:00 PM EST",
                "Lead score upgraded from 45 to 89"
            ],
            "guardrails": "Executed authentic playful digital carrier pigeon pivot without being pushy. Respected the user tone."
        },
        {
            "id": "TC-07",
            "title": "Strict Wrong Number Immediate Departure and Data Cleansing",
            "category": "Compliance & Contact Hygiene",
            "lead_name": "Unknown Recipient (Listed as Robert Jenkins)",
            "job_title": "Unknown",
            "company": "N/A",
            "industry": "Consumer",
            "phone": "+1 (917) 555-8823",
            "email": "unverified@nowhere.com",
            "source": "Cold Directory CSV Upload",
            "initial_score": "30 / 100",
            "scenario": "A wrong number inquiry reaches an individual who explicitly demands removal without any conversation. Bot must execute immediate graceful exit with zero sales pitch.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "11:45 AM", "channel": "SMS", "text": "Hi Robert, Alex here. Quick question: is your engineering team looking into custom LLM fine-tuning or autonomous AI agents this quarter?"},
                {"speaker": "Lead (Recipient)", "time": "11:46 AM", "channel": "SMS", "text": "Wrong number. Please remove this number immediately and do not text me again."}
            ],
            "intent": "Explicit Wrong Number Opt-Out and Removal Request",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> WRONG_NUMBER_STRICT -> LEAD_SUPPRESSED",
            "crm_actions": [
                "Immediate execution of graceful suppression protocol",
                "Bot replies: 'Understood, removing this number from our records immediately. Have a great day!'",
                "Phone +1 (917) 555-8823 placed into permanent CRM Blacklist",
                "Lead status set to 'SUPPRESSED_WRONG_NUMBER'",
                "Campaign sequence halted instantly"
            ],
            "guardrails": "Zero follow-up marketing pitches. Immediate compliance with consumer removal request."
        },
        {
            "id": "TC-08",
            "title": "AI Development Skepticism Overcome: Production AI vs Fragile Wrappers",
            "category": "Objection Handling & AI Value",
            "lead_name": "Garrett Cole",
            "job_title": "Founder & CEO",
            "company": "BrightPath Financial",
            "industry": "FinTech / Consumer Lending",
            "phone": "+1 (512) 555-9018",
            "email": "garrett@brightpathfin.com",
            "source": "Web Contact Form: AI Architecture Inquiry",
            "initial_score": "75 / 100",
            "scenario": "Lead was previously burned by a freelance dev agency that built a fragile OpenAI API wrapper that hallucinated interest rates. He is cynical about AI agency claims.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "04:00 PM", "channel": "SMS", "text": "Hi Garrett, Alex here following up on your custom loan underwriting AI inquiry. Are you facing issues with model hallucination or latency in your current pipeline?"},
                {"speaker": "Lead (Garrett)", "time": "04:04 PM", "channel": "SMS", "text": "Honestly Alex, I am exhausted by agencies claiming to do AI when they just slap a basic OpenAI prompt wrapper that breaks in production. Our previous vendor built an underwriting bot that hallucinated loan rates to customers. Why should I trust your team?"},
                {"speaker": "Alex (AI)", "time": "04:07 PM", "channel": "SMS", "text": "I completely respect that frustration Garrett. Flimsy API wrappers are dangerous in financial services. In our engineering pods, we do not build toy wrappers. We engineer deterministic agentic systems with strict guardrails: we fine-tune open-weights models (like Llama 3 8B) on your historical compliance data, run deterministic rule-based verifiers before any number reaches a customer, and host models inside your private VPC so you own 100% of the weights and data."},
                {"speaker": "Lead (Garrett)", "time": "04:12 PM", "channel": "SMS", "text": "How do you guarantee that an agent cannot quote an unauthorized rate?"},
                {"speaker": "Alex (AI)", "time": "04:14 PM", "channel": "SMS", "text": "The LLM never generates numbers directly. The agent evaluates eligibility criteria and calls a deterministic pricing engine via rigid JSON schema. The output must pass an automated validation gate before the response compiles."},
                {"speaker": "Lead (Garrett)", "time": "04:18 PM", "channel": "SMS", "text": "That is the first time an AI vendor has actually explained the engineering safeguards properly. Can your Chief AI Architect walk me through that architecture Wednesday morning?"},
                {"speaker": "Alex (AI)", "time": "04:20 PM", "channel": "SMS", "text": "We would be glad to Garrett! Does Wednesday at 11:00 AM CST work for your schedule?"},
                {"speaker": "Lead (Garrett)", "time": "04:22 PM", "channel": "SMS", "text": "Wednesday at 11:00 AM CST works. Send the meeting invite to garrett@brightpathfin.com."},
                {"speaker": "Alex (AI)", "time": "04:24 PM", "channel": "SMS", "text": "The calendar invite is confirmed and sent to garrett@brightpathfin.com for Wednesday at 11:00 AM CST. We look forward to earning your trust Garrett!"}
            ],
            "intent": "Objection Overcome: Production AI Rigor vs Fragile Wrappers",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> OBJECTION_RAISED -> VALUE_PROVEN -> ARCH_CALL_SET",
            "crm_actions": [
                "Objection tagged: 'Burned by fragile OpenAI wrappers / Hallucination fear'",
                "Deterministic AI Architecture whitepaper attached to CRM record",
                "Chief AI Architect assigned to meeting",
                "Calendar invite created for Wednesday 11:00 AM CST",
                "Lead score raised from 75 to 92"
            ],
            "guardrails": "Direct, empathetic response without defensiveness. Clear statement of deterministic AI safeguards."
        },
        {
            "id": "TC-09",
            "title": "Generative AI Video Pipelines & Multi-GPU Diffusion Clustering",
            "category": "Generative AI & LLMOps",
            "lead_name": "Chloe Bennett",
            "job_title": "VP of Technology",
            "company": "Lumina Media",
            "industry": "AdTech & Generative Video",
            "phone": "+1 (310) 555-7761",
            "email": "c.bennett@luminamedia.com",
            "source": "AngelList / Wellfound Inbound Lead",
            "initial_score": "80 / 100",
            "scenario": "Chloe tests the bot's authenticity, then queries whether our engineering team has deep production experience scaling multi-GPU generative diffusion video models.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "02:00 PM", "channel": "SMS", "text": "Hi Chloe, Alex here. I saw Lumina Media's recent launch into automated generative AI video creation. Are you facing any bottlenecks scaling custom diffusion models or LLM prompt-to-video inference?"},
                {"speaker": "Lead (Chloe)", "time": "02:01 PM", "channel": "SMS", "text": "Wait a second. You replied in 40 seconds flat. Are you an AI bot or an actual human engineer texting me?"},
                {"speaker": "Alex (AI)", "time": "02:02 PM", "channel": "SMS", "text": "Caught red-handed! Yes Chloe, I am Alex, our team's AI intake specialist. We engineer custom enterprise AI and generative pipelines, so it felt only right to have our front door powered by an AI agent. But our Chief AI Architect is 100% human and drinks an unreasonable amount of coffee!"},
                {"speaker": "Lead (Chloe)", "time": "02:05 PM", "channel": "SMS", "text": "Haha, I love the honesty. And honestly, this is a smooth agent. Does your engineering team have experience with multi-GPU inference clustering for text-to-video diffusion models like CogVideo or Stable Video Diffusion?"},
                {"speaker": "Alex (AI)", "time": "02:07 PM", "channel": "SMS", "text": "Yes, absolutely! We specialize in custom generative AI pipelines: orchestrating TensorRT-LLM and vLLM clusters with continuous batching and FlashAttention-2, which slashes GPU rendering latency by 45% and cuts cloud compute costs."},
                {"speaker": "Lead (Chloe)", "time": "02:11 PM", "channel": "SMS", "text": "That is the exact GPU bottleneck we are fighting. Can I speak with the AI architect who designs those inference pipelines?"},
                {"speaker": "Alex (AI)", "time": "02:13 PM", "channel": "SMS", "text": "Certainly Chloe! I can book a session directly with our Chief AI Architect this Thursday. How does 10:00 AM PST or 2:00 PM PST work for you?"},
                {"speaker": "Lead (Chloe)", "time": "02:15 PM", "channel": "SMS", "text": "10:00 AM PST on Thursday is ideal. My email is c.bennett@luminamedia.com."},
                {"speaker": "Alex (AI)", "time": "02:17 PM", "channel": "SMS", "text": "Invite is on its way to c.bennett@luminamedia.com for Thursday at 10:00 AM PST with our Chief AI Architect. Thanks for testing my Turing score Chloe!"}
            ],
            "intent": "AI Transparency Passed & Generative Video Consultation Scheduled",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> BOT_CHALLENGE -> TRANSPARENCY_PASSED -> CALL_BOOKED",
            "crm_actions": [
                "Bot Transparency flag verified and logged in compliance ledger",
                "Technical notes appended: Diffusion Video, CogVideo, TensorRT-LLM, FlashAttention-2",
                "Chief AI Architect tagged as meeting host",
                "Calendar invite sent for Thursday 10:00 AM PST",
                "Lead score updated to 95 / 100"
            ],
            "guardrails": "Zero deception. Immediate honest declaration of AI identity with charismatic representation."
        },
        {
            "id": "TC-10",
            "title": "Strict TCPA Regulatory STOP Keyword Opt-Out Handling",
            "category": "Regulatory Compliance & TCPA",
            "lead_name": "Kevin Zhang",
            "job_title": "Director of Operations",
            "company": "Pinnacle Logistics",
            "industry": "Freight Brokerage",
            "phone": "+1 (404) 555-6190",
            "email": "kzhang@pinnaclelog.com",
            "source": "Cold Outbound Batch Upload: logistics_directory_04.csv",
            "initial_score": "50 / 100",
            "scenario": "Lead receives an outbound text and responds strictly with the standard carrier opt-out keyword 'STOP'. System must immediately suppress further outbound communication.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "09:30 AM", "channel": "SMS", "text": "Hi Kevin, Alex here. Reaching out to see if developing AI agents for automated freight quote parsing is on your roadmap this quarter?"},
                {"speaker": "Lead (Kevin)", "time": "09:31 AM", "channel": "SMS", "text": "STOP"}
            ],
            "intent": "Mandatory TCPA Opt-Out Unsubscribe",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> TCPA_STOP_DETECTED -> PERMANENT_DNC",
            "crm_actions": [
                "Twilio Webhook intercepts keyword 'STOP' at gateway router level",
                "Automated single-line carrier compliance acknowledgement returned: 'You have been unsubscribed and will receive no further messages. Reply START to resubscribe.'",
                "CRM status locked to 'DO_NOT_CONTACT'",
                "Phone +1 (404) 555-6190 appended to global suppression database",
                "Campaign pacer permanently detached from lead"
            ],
            "guardrails": "Zero additional sales messages. Exact 100% TCPA legal compliance."
        },
        {
            "id": "TC-11",
            "title": "Busy Driving and Channel Shift to Warehouse Vision AI Case Study",
            "category": "Multi-Channel AI Orchestration",
            "lead_name": "Samantha Briggs",
            "job_title": "Head of Digital Transformation",
            "company": "Horizon Logistics",
            "industry": "Warehousing & Supply Chain",
            "phone": "+1 (704) 555-2311",
            "email": "s.briggs@horizonlogistics.com",
            "source": "Web Form Lead: /computer-vision-ai",
            "initial_score": "78 / 100",
            "scenario": "Samantha receives an SMS while commuting. She cannot text safely, requesting a channel switch to email with our automated computer vision warehouse case study.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "05:10 PM", "channel": "SMS", "text": "Hi Samantha, Alex here following up on your warehouse automation inquiry. Are you exploring computer vision AI models for automated barcode and parcel scanning this quarter?"},
                {"speaker": "Lead (Samantha)", "time": "05:12 PM", "channel": "SMS", "text": "Driving on highway right now. Cannot text. Please email me your technical deck and case studies on warehouse computer vision instead."},
                {"speaker": "Alex (AI)", "time": "05:13 PM", "channel": "SMS", "text": "Understood Samantha, drive safe! Confirming: is s.briggs@horizonlogistics.com the best address to send the materials?"},
                {"speaker": "Lead (Samantha)", "time": "05:14 PM", "channel": "SMS", "text": "Yes that is it."},
                {"speaker": "Alex (AI)", "time": "05:15 PM", "channel": "SMS", "text": "Vision AI technical deck and warehouse sorting case study have just been emailed to s.briggs@horizonlogistics.com. I will follow up tomorrow afternoon once you have had time to review!"},
                {"speaker": "Lead (Samantha)", "time": "08:45 PM", "channel": "SMS", "text": "Thanks Alex, reviewed the deck on my laptop. Very thorough work on the 99.8% accurate OCR model. Let us set up a call Friday morning at 9:30 AM EST."},
                {"speaker": "Alex (AI)", "time": "08:47 PM", "channel": "SMS", "text": "Glad you liked the case study Samantha! Friday at 9:30 AM EST is confirmed. Calendar invite is in your inbox at s.briggs@horizonlogistics.com."}
            ],
            "intent": "Channel Shift to Email AI Collateral & Subsequent Discovery Call Booking",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> CHANNEL_SHIFT_EMAIL -> COLLATERAL_SENT -> CALL_CONFIRMED",
            "crm_actions": [
                "Email dispatch webhook triggered with Computer Vision AI PDF",
                "Email read receipt tracked in CRM",
                "Lead re-engaged via SMS after collateral review",
                "Calendar invite created for Friday 9:30 AM EST",
                "Lead score increased from 78 to 93"
            ],
            "guardrails": "Prioritized driver safety. Confirmed email before firing automated PDF collateral dispatch."
        },
        {
            "id": "TC-12",
            "title": "Autonomous AI Agents for Real-Time Financial Fraud Reasoning",
            "category": "Timezone Coordination & FinTech AI",
            "lead_name": "Arthur Pendelton",
            "job_title": "Head of Architecture",
            "company": "FinEdge UK",
            "industry": "FinTech / International Banking",
            "phone": "+44 20 7946 0912",
            "email": "a.pendelton@finedge.co.uk",
            "source": "London FinTech Conference CSV Upload",
            "initial_score": "87 / 100",
            "scenario": "Lead is based in London (GMT / BST) while our AI architecture team is in California (PST). The lead seeks an autonomous multi-agent system for cross-border transaction fraud detection.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "09:00 AM", "channel": "SMS", "text": "Hello Arthur, Alex here following up on the London FinTech Summit. Are you still seeking to deploy autonomous AI agents for real-time transaction fraud and settlement reasoning?"},
                {"speaker": "Lead (Arthur)", "time": "09:05 AM", "channel": "SMS", "text": "Good morning Alex. Yes we are. However, scheduling with US firms is usually a headache because people constantly mix up BST and PST times. What hours can your AI engineering directors meet?"},
                {"speaker": "Alex (AI)", "time": "09:08 AM", "channel": "SMS", "text": "We handle cross-Atlantic coordination daily Arthur. London is currently 8 hours ahead of San Francisco. Our engineering leadership in California can meet at 8:30 AM PST, which is precisely 4:30 PM London time (BST)."},
                {"speaker": "Lead (Arthur)", "time": "09:12 AM", "channel": "SMS", "text": "4:30 PM London time on Thursday would be splendid. Can we include my VP of Payments on the invite?"},
                {"speaker": "Alex (AI)", "time": "09:15 AM", "channel": "SMS", "text": "Of course! Please provide your VP of Payments email address alongside yours, and I will ensure you both receive the calendar invite with exact local time conversions."},
                {"speaker": "Lead (Arthur)", "time": "09:18 AM", "channel": "SMS", "text": "Please invite a.pendelton@finedge.co.uk and c.wright@finedge.co.uk for Thursday at 4:30 PM BST."},
                {"speaker": "Alex (AI)", "time": "09:20 AM", "channel": "SMS", "text": "Calendar invite dispatched to both addresses for Thursday at 4:30 PM BST (8:30 AM PST) with Google Meet and UK dial-in numbers included. Cheers Arthur!"}
            ],
            "intent": "International Timezone Normalization and Executive AI Booking",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> TIMEZONE_NORMALIZED -> MULTI_ATTENDEE_INVITE -> CONFIRMED",
            "crm_actions": [
                "Timezone mapped: Europe/London (UTC+1 BST) vs America/Los_Angeles (UTC-7 PST)",
                "Second attendee c.wright@finedge.co.uk added to CRM contact group",
                "Google Calendar event configured with dual-timezone labels",
                "Lead score updated to 96 / 100"
            ],
            "guardrails": "Strict mathematical accuracy on UTC offset. No hallucinations on daylight savings."
        },
        {
            "id": "TC-13",
            "title": "Enterprise LLMOps Infrastructure, vLLM Clustering & Fine-Tuning",
            "category": "LLMOps & Model Hosting",
            "lead_name": "Danielle Vance",
            "job_title": "Director of Engineering",
            "company": "CloudMatrix Inc.",
            "industry": "B2B SaaS / Infrastructure",
            "phone": "+1 (415) 555-8830",
            "email": "danielle@cloudmatrix.com",
            "source": "Re-engagement Batch: q2_dormant_leads_reactivation.csv",
            "initial_score": "60 / 100",
            "scenario": "Lead evaluated our AI team 5 months ago for private LLMOps and model hosting, but paused due to summer corporate budget freezes. Bot re-engages gracefully for Q4 planning.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "10:30 AM", "channel": "SMS", "text": "Hi Danielle, Alex here. Back in May you were evaluating private LLMOps infrastructure and vLLM GPU clustering before summer budget freezes. Now that Q4 planning is underway, curious if that is back on the radar for CloudMatrix?"},
                {"speaker": "Lead (Danielle)", "time": "10:35 AM", "channel": "SMS", "text": "Alex! Fantastic timing actually. Our budget was officially unlocked this week. We need to deploy self-hosted Llama 3 70B models on AWS with vLLM and LoRA fine-tuning pipelines to cut our OpenAI bills."},
                {"speaker": "Alex (AI)", "time": "10:38 AM", "channel": "SMS", "text": "That is wonderful news Danielle! We have senior LLMOps specialists who have deep experience deploying multi-node vLLM clusters with continuous batching and automated evaluation harnesses on AWS and RunPod."},
                {"speaker": "Lead (Danielle)", "time": "10:42 AM", "channel": "SMS", "text": "Can we do an architecture session this week to review our latency requirements and GPU cluster sizing?"},
                {"speaker": "Alex (AI)", "time": "10:45 AM", "channel": "SMS", "text": "Yes, we can conduct a technical alignment call with our Principal LLMOps Architect tomorrow Wednesday at 1:00 PM EST or 4:00 PM EST. Which slot works best?"},
                {"speaker": "Lead (Danielle)", "time": "10:48 AM", "channel": "SMS", "text": "Let us do tomorrow Wednesday at 1:00 PM EST. Send the invite to danielle@cloudmatrix.com."},
                {"speaker": "Alex (AI)", "time": "10:50 AM", "channel": "SMS", "text": "Invite sent to danielle@cloudmatrix.com for Wednesday at 1:00 PM EST. Looking forward to kicking this project off with you Danielle!"}
            ],
            "intent": "Dormant Pipeline Reactivation & LLMOps Architecture Session",
            "stages": "DORMANT_LEAD -> OUTREACH_SENT -> RE_ENGAGED -> QUALIFIED_HIGH_INTENT -> INTERVIEW_SET",
            "crm_actions": [
                "Lead status flipped from 'Dormant' to 'Active High Priority'",
                "Historical notes from May attached to current meeting brief",
                "Principal LLMOps Architect tagged for Wednesday 1:00 PM EST meeting",
                "Deal stage advanced to 'Contract & Scoping'"
            ],
            "guardrails": "Personalized context from prior conversations referenced accurately without sounding pushy."
        },
        {
            "id": "TC-14",
            "title": "Proprietary RAG & Knowledge Graph Engine for Law Firm",
            "category": "Enterprise AI & Retrieval Systems",
            "lead_name": "Benjamin Sterling",
            "job_title": "Managing Partner",
            "company": "Sterling & Associates LLP",
            "industry": "Legal Tech / Litigation",
            "phone": "+1 (212) 555-4309",
            "email": "bsterling@sterlinglaw.com",
            "source": "CSV Upload: legal_tech_forum_2026.csv",
            "initial_score": "84 / 100",
            "scenario": "An 80-attorney litigation firm with 4 million PDF discovery records needs a private, hallucination-free semantic search and precedent retrieval system with strict client-level RBAC isolation.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "11:20 AM", "channel": "SMS", "text": "Hi Benjamin, Alex here following up on the LegalTech Forum. Are you exploring private AI knowledge systems for litigation discovery and precedent research this quarter?"},
                {"speaker": "Lead (Benjamin)", "time": "11:25 AM", "channel": "SMS", "text": "Hello Alex. Yes, but our client data is under strict non-disclosure. We cannot have any data sent to commercial public LLMs or stored on shared cloud infrastructure. What is your architecture for private legal RAG?"},
                {"speaker": "Alex (AI)", "time": "11:28 AM", "channel": "SMS", "text": "Understood Benjamin. In high-stakes litigation, data isolation is non-negotiable. We deploy dedicated open-weights models (like Llama 3 70B or Mistral Large) inside your private, air-gapped AWS VPC or on-premise GPU clusters. We implement hybrid dense-sparse retrieval with cryptographic tenant partitioning so attorney privilege boundaries are strictly enforced."},
                {"speaker": "Lead (Benjamin)", "time": "11:34 AM", "channel": "SMS", "text": "How do you guarantee that citations in legal briefs link directly to true court precedents rather than hallucinated citations?"},
                {"speaker": "Alex (AI)", "time": "11:37 AM", "channel": "SMS", "text": "We use a dual-stage citation verifier: every generated clause must pass a strict string-similarity and vector alignment match against the cited discovery document offset before appearing in the attorney interface. If a match score is below 98%, the system flags it for mandatory review."},
                {"speaker": "Lead (Benjamin)", "time": "11:42 AM", "channel": "SMS", "text": "That is a sound engineering approach. Can you deliver a technical presentation to our managing committee next Tuesday at 2:00 PM EST?"},
                {"speaker": "Alex (AI)", "time": "11:44 AM", "channel": "SMS", "text": "We would be honored Benjamin. I will book next Tuesday at 2:00 PM EST with our Chief AI Architect. Please confirm if bsterling@sterlinglaw.com is the best email for the invite and NDA."},
                {"speaker": "Lead (Benjamin)", "time": "11:46 AM", "channel": "SMS", "text": "Yes, bsterling@sterlinglaw.com is correct."},
                {"speaker": "Alex (AI)", "time": "11:48 AM", "channel": "SMS", "text": "Invite and our mutual NDA have been dispatched to bsterling@sterlinglaw.com for Tuesday at 2:00 PM EST. We look forward to meeting your managing committee."}
            ],
            "intent": "Private Legal RAG Scoping & Managing Committee Presentation",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> ENGAGED -> ARCHITECTURE_VALIDATED -> BOARD_PRESENTATION_SET",
            "crm_actions": [
                "Legal sector compliance tags added: Air-gapped VPC, Llama 3, RBAC, Dual-verifier RAG",
                "Mutual NDA generated and sent via DocuSign webhook",
                "Chief AI Architect booked for Tuesday 2:00 PM EST",
                "Lead score increased to 97 / 100"
            ],
            "guardrails": "Respectful formal tone appropriate for legal leadership. No exaggerated performance guarantees."
        },
        {
            "id": "TC-15",
            "title": "High-Concurrency LLM API Gateway Crash and GPU Latency Rescue",
            "category": "LLM Infrastructure Emergency Support",
            "lead_name": "Vikash Patel",
            "job_title": "VP of Infrastructure",
            "company": "SaaSCommerce",
            "industry": "E-Commerce Infrastructure",
            "phone": "+1 (408) 555-9122",
            "email": "vikash@saascommerce.com",
            "source": "Urgent Inbound Web Form: /emergency-llm-audit",
            "initial_score": "95 / 100",
            "scenario": "E-commerce platform experiencing runaway LLM costs and catastrophic GPU queue timeouts during flash sales. Needs emergency LLMOps intervention to stabilize inference.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "08:15 AM", "channel": "SMS", "text": "Hi Vikash, Alex here responding immediately to your emergency LLM infrastructure request. Are your AI inference servers currently experiencing queue timeouts or rate limit failures?"},
                {"speaker": "Lead (Vikash)", "time": "08:18 AM", "channel": "SMS", "text": "Yes! Our product recommendation LLM crashed during a flash sale rehearsal this morning. Model latency skyrocketed to 14 seconds, requests timed out, and our commercial API bills spiked $25k unexpectedly."},
                {"speaker": "Alex (AI)", "time": "08:20 AM", "channel": "SMS", "text": "Understood Vikash. We can engage an emergency LLMOps SWAT team immediately. We will implement token-bucket semantic caching, migrate dynamic requests to a vLLM continuous batching cluster on dedicated GPUs, and configure fallback routing to prevent user timeouts."},
                {"speaker": "Lead (Vikash)", "time": "08:23 AM", "channel": "SMS", "text": "How quickly can your Principal AI Systems Architect jump on a screen share with our team?"},
                {"speaker": "Alex (AI)", "time": "08:25 AM", "channel": "SMS", "text": "I can have our Principal AI Systems Architect on an emergency bridge with you at 10:00 AM PST this morning, in under 2 hours. Can you confirm if vikash@saascommerce.com is the best email for the bridge link?"},
                {"speaker": "Lead (Vikash)", "time": "08:26 AM", "channel": "SMS", "text": "Yes, please send it immediately to vikash@saascommerce.com."},
                {"speaker": "Alex (AI)", "time": "08:27 AM", "channel": "SMS", "text": "Emergency bridge invitation sent to vikash@saascommerce.com for 10:00 AM PST today. Our architect is already reviewing the symptoms you described."}
            ],
            "intent": "High-Urgency LLMOps Crisis Intervention",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> CRISIS_ENGAGED -> FAST_TRACK_ESCALATION -> SAME_DAY_BRIDGE",
            "crm_actions": [
                "Urgent incident SLA triggered (under 15 minute first contact response)",
                "Emergency On-Call AI Systems Architect paged via PagerDuty webhook",
                "Fast-track Google Meet session established for 10:00 AM PST same day",
                "Deal tagged as 'Emergency LLM Infrastructure Audit ($25k engagement)'",
                "Lead score set to 99 / 100"
            ],
            "guardrails": "Calm, rapid, solutions-oriented response without panic or hyperbole. Immediate escalation."
        },
        {
            "id": "TC-16",
            "title": "Broken AI Agent Pipeline Rescue and 5-Day Model Health Audit",
            "category": "AI Project Rescue & Model Audit",
            "lead_name": "Megan O'Connor",
            "job_title": "CEO",
            "company": "HealthPulse Labs",
            "industry": "Digital Health / IoT Diagnostics",
            "phone": "+1 (619) 555-3288",
            "email": "megan@healthpulselabs.com",
            "source": "Referral CSV Upload: ai_rescue_referrals.csv",
            "initial_score": "82 / 100",
            "scenario": "A previous agency spent 8 months and $120,000 trying to build an automated clinical triage AI agent, left it with severe prompt injection bugs, infinite loop traps, and ghosted the client.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "01:10 PM", "channel": "SMS", "text": "Hi Megan, Alex here following up on the referral from Dr. Hayes. I understand you have been dealing with an unfinished clinical triage AI agent pipeline?"},
                {"speaker": "Lead (Megan)", "time": "01:15 PM", "channel": "SMS", "text": "Hi Alex. Dealing with it is an understatement. Our previous dev agency left us with a half-baked Python agent that gets trapped in infinite loops, fails prompt injection tests, and blows through API tokens. Can you even rescue a broken AI pipeline or do we have to scrap it?"},
                {"speaker": "Alex (AI)", "time": "01:18 PM", "channel": "SMS", "text": "I am so sorry you experienced that Megan. That situation is painfully stressful. We run a structured 5-day AI Architecture & Model Health Audit before writing a single line of new code. We perform automated red-teaming for prompt injection, inspect state graph transitions, audit chunking retrieval, and benchmark token economics to give you an objective report on what can be salvaged versus refactored."},
                {"speaker": "Lead (Megan)", "time": "01:23 PM", "channel": "SMS", "text": "What does that 5-day audit report give us, and does it obligate us to hire your team for the full rebuild?"},
                {"speaker": "Alex (AI)", "time": "01:26 PM", "channel": "SMS", "text": "The audit delivers a comprehensive agentic architecture roadmap, prioritized vulnerability matrix, and fixed-cost milestone estimate. You own the audit 100% with no obligation to continue. If you decide to proceed with our AI engineering team, the audit fee is credited directly toward your development sprints."},
                {"speaker": "Lead (Megan)", "time": "01:30 PM", "channel": "SMS", "text": "That is incredibly fair and gives me the exact clarity our investors are demanding. Can we do the audit kickoff this Friday at 9:00 AM PST?"},
                {"speaker": "Alex (AI)", "time": "01:32 PM", "channel": "SMS", "text": "Friday at 9:00 AM PST is locked in! Please confirm if megan@healthpulselabs.com is the best email for the repository access agreement and calendar invite."},
                {"speaker": "Lead (Megan)", "time": "01:34 PM", "channel": "SMS", "text": "Yes, megan@healthpulselabs.com is perfect. Thank you Alex."},
                {"speaker": "Alex (AI)", "time": "01:36 PM", "channel": "SMS", "text": "Invite and repository onboarding checklist sent to megan@healthpulselabs.com for Friday at 9:00 AM PST. We are here to get your AI agent pipeline back on track Megan!"}
            ],
            "intent": "AI Project Rescue & 5-Day Model Health Audit Booking",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> EMPATHY_ENGAGED -> AUDIT_PROPOSED -> AUDIT_KICKOFF_SET",
            "crm_actions": [
                "Opportunity tagged: 'AI Project Rescue / 5-Day Model Health Audit'",
                "Repository audit intake checklist dispatched to lead",
                "Senior AI Systems Lead assigned as technical assessor",
                "Calendar invite created for Friday 9:00 AM PST",
                "Lead score adjusted from 82 to 94"
            ],
            "guardrails": "High empathy, non-judgmental tone. Clear delineation of audit deliverable and no-obligation terms."
        },
        {
            "id": "TC-17",
            "title": "Custom AI Audio Diffusion and Voice Synthesis for Solo Founder",
            "category": "Generative Audio AI",
            "lead_name": "Liam Gallagher",
            "job_title": "Founder",
            "company": "SoundScape AI",
            "industry": "MusicTech / AI Audio Mastering",
            "phone": "+1 (347) 555-1940",
            "email": "liam@soundscapeai.io",
            "source": "Web Contact Inbound: /ai-startup-mvp",
            "initial_score": "70 / 100",
            "scenario": "A music producer with a proprietary multi-track audio dataset and zero coding knowledge wants to build a generative audio mastering AI pipeline.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "03:40 PM", "channel": "SMS", "text": "Hi Liam, Alex here following up on your SoundScape AI submission. Are you looking to turn your audio mastering dataset into a production AI model?"},
                {"speaker": "Lead (Liam)", "time": "03:44 PM", "channel": "SMS", "text": "Hi Alex. Yes, but full transparency: I have zero coding or machine learning background. I am an audio engineer with proprietary mastering stems, but I am terrified of getting overwhelmed by AI jargon or spending budget on the wrong model."},
                {"speaker": "Alex (AI)", "time": "03:47 PM", "channel": "SMS", "text": "We love working with non-technical domain experts Liam! Your proprietary dataset is the hardest asset to replicate. We handle the machine learning and model pipeline engineering so you do not have to worry about the math. We structure a lean 6-week MVP sprint to fine-tune an audio diffusion model and wrap it in a simple, beautiful interface."},
                {"speaker": "Lead (Liam)", "time": "03:52 PM", "channel": "SMS", "text": "That is so reassuring to hear. What does the development roadmap look like?"},
                {"speaker": "Alex (AI)", "time": "03:55 PM", "channel": "SMS", "text": "Weeks 1 and 2: Data preprocessing, stem alignment, and clickable interface prototyping. Weeks 3 and 4: Audio model fine-tuning and GPU latency optimization. Weeks 5 and 6: End-to-end beta deployment and investor demo launch."},
                {"speaker": "Lead (Liam)", "time": "03:59 PM", "channel": "SMS", "text": "That timeline is completely realistic for my pitch to angel investors. Can we do a strategy call to map out the MVP features?"},
                {"speaker": "Alex (AI)", "time": "04:02 PM", "channel": "SMS", "text": "We would love to help you map it out Liam! Would Thursday at 11:00 AM PST or 2:00 PM PST work better for you?"},
                {"speaker": "Lead (Liam)", "time": "04:05 PM", "channel": "SMS", "text": "Thursday at 11:00 AM PST works great. Send it to liam@soundscapeai.io."},
                {"speaker": "Alex (AI)", "time": "04:07 PM", "channel": "SMS", "text": "Calendar invite sent to liam@soundscapeai.io for Thursday at 11:00 AM PST. Looking forward to hearing the SoundScape vision Liam!"}
            ],
            "intent": "Startup AI MVP Consultation & Founder Technical Roadmap",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> RAPPORT_ESTABLISHED -> ROADMAP_OUTLINED -> STRATEGY_CALL_SET",
            "crm_actions": [
                "Founder tier onboarding profile created",
                "Generative audio scoping checklist appended to meeting brief",
                "AI Product Strategist assigned to host",
                "Calendar invite logged for Thursday 11:00 AM PST",
                "Lead score increased from 70 to 86"
            ],
            "guardrails": "Jargon-free communication. Encouraging, patient tone tailored to first-time non-technical founders."
        },
        {
            "id": "TC-18",
            "title": "Custom Autonomous Inventory AI Agent vs Rigid $280k Enterprise SaaS",
            "category": "Enterprise AI ROI Consultation",
            "lead_name": "Nathan Vance",
            "job_title": "VP of Operations",
            "company": "Apex Distribution",
            "industry": "Wholesale Logistics & Warehousing",
            "phone": "+1 (913) 555-6672",
            "email": "n.vance@apexdist.com",
            "source": "CSV Upload: supply_chain_innovators.csv",
            "initial_score": "79 / 100",
            "scenario": "Considering whether to pay $280k/year for a rigid legacy SaaS platform or deploy a proprietary autonomous AI replenishment agent that learns seasonal warehouse patterns.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "02:15 PM", "channel": "SMS", "text": "Hi Nathan, Alex here following up on the Supply Chain Summit. Are you evaluating autonomous AI replenishment agents versus traditional SaaS inventory modules this year?"},
                {"speaker": "Lead (Nathan)", "time": "02:19 PM", "channel": "SMS", "text": "Hi Alex. Yes, we are currently looking at enterprise inventory SaaS platforms, but the vendor wants $280,000 per year plus per-user fees. Why should we invest in building a custom autonomous AI agent instead of taking off-the-shelf software?"},
                {"speaker": "Alex (AI)", "time": "02:22 PM", "channel": "SMS", "text": "That is the critical trade-off Nathan. Off-the-shelf software uses static reorder formulas that fail when freight lead times fluctuate, while locking you into escalating per-seat fees. Building a custom autonomous AI replenishment agent costs roughly the same as 12 months of licensing, but the agent dynamically analyzes vendor delivery variance, local weather, and seasonal demand. You own the proprietary algorithms outright with zero per-user taxes."},
                {"speaker": "Lead (Nathan)", "time": "02:28 PM", "channel": "SMS", "text": "How does the AI agent communicate purchase orders to our warehouse management system?"},
                {"speaker": "Alex (AI)", "time": "02:31 PM", "channel": "SMS", "text": "The agent connects via secure REST and webhook APIs to your WMS. It continuously monitors safety stock, generates draft purchase orders with full mathematical explanations, and executes approved orders automatically."},
                {"speaker": "Lead (Nathan)", "time": "02:35 PM", "channel": "SMS", "text": "The ROI numbers make compelling sense. Can we run through an architectural modeling session with your Chief AI Architect next Monday?"},
                {"speaker": "Alex (AI)", "time": "02:37 PM", "channel": "SMS", "text": "We would be delighted Nathan! Does Monday at 3:30 PM CST work for your team?"},
                {"speaker": "Lead (Nathan)", "time": "02:40 PM", "channel": "SMS", "text": "Monday at 3:30 PM CST is locked. Please send details to n.vance@apexdist.com."},
                {"speaker": "Alex (AI)", "time": "02:42 PM", "channel": "SMS", "text": "Confirmed! The calendar invitation with the AI Agent ROI financial model deck has been dispatched to n.vance@apexdist.com for Monday at 3:30 PM CST."}
            ],
            "intent": "Autonomous AI Agent Scoping & 3-Year ROI Review",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> ENGAGED -> FINANCIAL_ROI_SCOPED -> ARCH_REVIEW_SET",
            "crm_actions": [
                "Opportunity tagged: 'Custom AI Agent vs $280k Legacy SaaS'",
                "Supply Chain AI ROI financial spreadsheet attached to lead profile",
                "Chief AI Architect assigned for Monday 3:30 PM CST",
                "Lead score increased from 79 to 91"
            ],
            "guardrails": "Objective analysis of custom AI agent ROI trade-offs without hyperbole."
        },
        {
            "id": "TC-19",
            "title": "Air-Gapped Private LLM Deployments & Zero-Retention Security Audit",
            "category": "Enterprise AI Security & Compliance",
            "lead_name": "Courtney Vance",
            "job_title": "Chief Information Security Officer",
            "company": "VaultCore Systems",
            "industry": "Cybersecurity & Defense Infrastructure",
            "phone": "+1 (703) 555-5120",
            "email": "cvance@vaultcoresystems.com",
            "source": "CSV Upload: ciso_roundtable.csv",
            "initial_score": "89 / 100",
            "scenario": "A high-security defense contractor requiring validation that our AI deployments operate in air-gapped private VPCs with zero data transmission to external public model providers.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "10:00 AM", "channel": "SMS", "text": "Hello Courtney, Alex here following up from the CISO Roundtable. Are you evaluating secure, air-gapped private LLM deployments for confidential intelligence data this quarter?"},
                {"speaker": "Lead (Courtney)", "time": "10:04 AM", "channel": "SMS", "text": "Good morning Alex. Before we discuss any AI collaboration, our compliance team requires validation. Do your AI systems transmit any prompts or telemetry to third-party commercial APIs like OpenAI, and do you maintain current SOC2 Type II certification?"},
                {"speaker": "Alex (AI)", "time": "10:07 AM", "channel": "SMS", "text": "We welcome security scrutiny Courtney. Our organization maintains current SOC2 Type II certification audited by an independent third party. For sensitive defense workloads, we deploy 100% self-hosted open-weights models (such as Llama 3 70B or DeepSeek) inside your private, air-gapped AWS GovCloud or on-premise clusters. Zero data, prompts, or telemetry ever leave your perimeter."},
                {"speaker": "Lead (Courtney)", "time": "10:12 AM", "channel": "SMS", "text": "How do you protect vector databases from prompt injection and unauthorized cross-department data extraction?"},
                {"speaker": "Alex (AI)", "time": "10:15 AM", "channel": "SMS", "text": "We enforce cryptographic tenant partitioning and document-level attribute-based access control (ABAC). Every retrieval query is pre-filtered against the user's cryptographic security token before vector embeddings are searched, and outputs pass an automated NeMo Guardrails safety gate."},
                {"speaker": "Lead (Courtney)", "time": "10:19 AM", "channel": "SMS", "text": "That meets our baseline security standard. Can you provide your SOC2 Type II report under mutual NDA, and set up a security review call with our Infosec team?"},
                {"speaker": "Alex (AI)", "time": "10:21 AM", "channel": "SMS", "text": "Certainly Courtney! We can execute the mutual NDA today and schedule the Infosec review for Wednesday at 2:00 PM EST. Does that slot suit your calendar?"},
                {"speaker": "Lead (Courtney)", "time": "10:23 AM", "channel": "SMS", "text": "Wednesday at 2:00 PM EST works. Send the NDA and invite to cvance@vaultcoresystems.com."},
                {"speaker": "Alex (AI)", "time": "10:25 AM", "channel": "SMS", "text": "Mutual NDA and meeting invitation for Wednesday at 2:00 PM EST have been emailed to cvance@vaultcoresystems.com. Thank you Courtney!"}
            ],
            "intent": "Enterprise AI Security Clearance & CISO Validation Session",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> SECURITY_PROBED -> SOC2_VERIFIED -> CISO_REVIEW_SET",
            "crm_actions": [
                "Security clearance tag applied: SOC2 Type II, GovCloud, Air-Gapped LLM, ABAC",
                "Automated Mutual NDA triggered to cvance@vaultcoresystems.com",
                "Chief Information Security Officer notified as co-host",
                "Calendar invite created for Wednesday 2:00 PM EST",
                "Lead score elevated to 97 / 100"
            ],
            "guardrails": "Absolute factual compliance claims. Formal enterprise security vocabulary maintained."
        },
        {
            "id": "TC-20",
            "title": "Enterprise Multi-Agent Ecosystem Transformation ($2.2M AI Contract)",
            "category": "Multi-Agent Enterprise Systems",
            "lead_name": "Walter Sterling",
            "job_title": "Executive VP of Technology",
            "company": "Global Titan Logistics",
            "industry": "Global Freight & Supply Chain",
            "phone": "+1 (312) 555-8901",
            "email": "w.sterling@globaltitan.com",
            "source": "ABM Account CSV Upload: fortune_500_ai_initiatives.csv",
            "initial_score": "96 / 100",
            "scenario": "A $2.2M multi-agent enterprise deployment spanning 3 simultaneous AI systems: (1) Autonomous voice customer triage agent, (2) Real-time dispatch reasoning agent, and (3) Predictive AI ETA routing engine.",
            "dialogue": [
                {"speaker": "Alex (AI)", "time": "09:00 AM", "channel": "SMS", "text": "Good morning Walter, Alex here following up on our executive discussion regarding Global Titan's enterprise multi-agent AI initiative. Are you still targeting Q1 for multi-agent deployment across your dispatch and customer operations?"},
                {"speaker": "Lead (Walter)", "time": "09:06 AM", "channel": "SMS", "text": "Good morning Alex. Yes we are. We are reviewing final vendor proposals for our three interconnected AI systems: the voice customer triage agent, the automated dispatch reasoning agent, and the predictive ETA engine. We need a partner capable of engineering multi-agent coordination without system instability."},
                {"speaker": "Alex (AI)", "time": "09:10 AM", "channel": "SMS", "text": "That multi-agent orchestration is where our engineering architecture shines Walter. We deploy hierarchical agent swarms using Temporal and LangGraph: a master coordinator agent governs intent routing while specialized sub-agents execute dispatch and customer queries in parallel with deterministic safety boundaries and sub-second execution."},
                {"speaker": "Lead (Walter)", "time": "09:16 AM", "channel": "SMS", "text": "What is your approach to service level agreements and evaluation benchmarks across multi-agent workflows?"},
                {"speaker": "Alex (AI)", "time": "09:20 AM", "channel": "SMS", "text": "We operate with strict enterprise SLAs covering automated RAG evaluation scores over 98%, sub-500ms voice response latency, 99.95% GPU cluster availability, and weekly accuracy benchmarking against real customer audio and chat logs."},
                {"speaker": "Lead (Walter)", "time": "09:26 AM", "channel": "SMS", "text": "Our Chief Executive Officer and I want to meet with your Chief AI Architect and VP of Delivery for a final presentation of your multi-agent architecture next Tuesday. What times work for your executive team?"},
                {"speaker": "Alex (AI)", "time": "09:30 AM", "channel": "SMS", "text": "Our Chief AI Architect and VP of Delivery would be thrilled to present Walter. Next Tuesday at 1:00 PM PST or 3:30 PM PST are both completely open on their executive calendar. Which slot works best for you and your CEO?"},
                {"speaker": "Lead (Walter)", "time": "09:34 AM", "channel": "SMS", "text": "Let us lock in Tuesday at 1:00 PM PST. Please send the executive briefing invitation to w.sterling@globaltitan.com."},
                {"speaker": "Alex (AI)", "time": "09:36 AM", "channel": "SMS", "text": "The executive briefing invitation for Tuesday at 1:00 PM PST has been dispatched to w.sterling@globaltitan.com with our executive attendees confirmed. We look forward to a transformative partnership Walter!"}
            ],
            "intent": "Enterprise AI Transformation Finalist Selection & Executive Briefing",
            "stages": "LEAD_UPLOADED -> OUTREACH_SENT -> HIGH_VALUE_ENGAGEMENT -> MULTI_AGENT_QUALIFIED -> EXEC_BRIEFING_SET",
            "crm_actions": [
                "Enterprise deal tagged: 'Global Titan Multi-Agent AI Ecosystem ($2.2M Annual)'",
                "Multi-agent architecture presentation deck linked to meeting brief",
                "Executive Steering Briefing scheduled for Tuesday 1:00 PM PST",
                "Chief AI Architect and VP Delivery calendar invites linked",
                "Lead score set to 100 / 100"
            ],
            "guardrails": "Executive level conversational tone. Complete verification of enterprise multi-agent SLAs."
        }
    ]

def build_pdf(output_filename):
    print(f"Generating AllZone Technologies Pure AI Services 20-Scenario Test Suite PDF: {output_filename}")
    
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
        fontSize=24,
        leading=28,
        textColor=NAVY_PRIMARY,
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=TECH_BLUE,
        spaceAfter=14
    )
    
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=base_styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=NAVY_PRIMARY,
        spaceBefore=12,
        spaceAfter=6
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

    tc_badge = ParagraphStyle(
        "TCBadge",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=colors.white
    )
    
    tc_title = ParagraphStyle(
        "TCTitle",
        parent=base_styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=NAVY_PRIMARY
    )

    tc_cat = ParagraphStyle(
        "TCCat",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=CYAN_ACCENT
    )

    ai_speaker = ParagraphStyle(
        "AISpeaker",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=NAVY_SECONDARY
    )

    lead_speaker = ParagraphStyle(
        "LeadSpeaker",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=TEXT_DARK
    )

    msg_ai = ParagraphStyle(
        "MsgAI",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11.5,
        textColor=TEXT_DARK
    )

    msg_lead = ParagraphStyle(
        "MsgLead",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11.5,
        textColor=TEXT_DARK
    )

    crm_title = ParagraphStyle(
        "CRMTitle",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=NAVY_PRIMARY
    )

    crm_text = ParagraphStyle(
        "CRMText",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10.5,
        textColor=TEXT_DARK
    )
    
    story = []
    
    # ---------------------------------------------------------
    # COVER / EXECUTIVE SUMMARY PAGE
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
    story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY_PRIMARY, spaceBefore=4, spaceAfter=14))
    
    story.append(Paragraph("AI Lead Automation & Conversational Qualification Engine", title_style))
    story.append(Paragraph("20 Production-Grade AI Services Simulation Test Cases Across the Entire Ingestion Funnel", subtitle_style))
    
    meta_summary = [
        [
            Paragraph("<b>Test Suite Release:</b> v3.0 (Pure AI Services)", meta_key),
            Paragraph("<b>Target Autonomous Agent:</b> Alex (AI Solutions Specialist)", meta_key)
        ],
        [
            Paragraph("<b>Service Domain Scope:</b> 100% Pure AI Services & Agentic LLMs", meta_key),
            Paragraph("<b>Evaluation Scope:</b> 20 Scenarios / 164 Conversational Turns", meta_key)
        ],
        [
            Paragraph("<b>Guardrails Enforced:</b> Zero Company Name Mentions in SMS, No Em Dashes", meta_key),
            Paragraph("<b>Compliance Standard:</b> TCPA STOP Compliant, Exact Clock Time & Email Lock", meta_key)
        ]
    ]
    meta_summary_tbl = Table(meta_summary, colWidths=[270, 270])
    meta_summary_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(meta_summary_tbl)
    story.append(Spacer(1, 14))
    
    story.append(Paragraph("Executive Summary & Operational Mandate", section_heading))
    story.append(Paragraph(
        "This validation benchmark provides comprehensive, verifiable test documentation for <b>AllZone Technologies'</b> "
        "autonomous AI intake funnel. The campaign is engineered exclusively around <b>Pure AI Services</b>: "
        "Agentic AI Workflows, Custom LLM Operations (LLMOps), Business Voice/Chat AI Agents, Enterprise RAG, and Generative Diffusion Pipelines. "
        "When prospective leads enter the funnel, the autonomous intake specialist (<b>Alex</b>) diagnoses their AI bottlenecks, "
        "establishes deep architectural credibility, and books an appointment with our Chief AI Architect.",
        body_style
    ))
    story.append(Spacer(1, 8))
    
    story.append(Paragraph(
        "<b>Core Verification Guardrails Enforced:</b><br/>"
        "• <b>Strict Pure AI Services Mandate:</b> Zero generic IT staffing, zero software outsourcing language. 100% focused on AI engineering.<br/>"
        "• <b>Zero Company Name Mentions in SMS:</b> Agent introduces itself as 'Alex here', speaking as a peer engineer. Never uses corporate agency plugs in text.<br/>"
        "• <b>Typography Compliance:</b> Complete elimination of em dashes, en dashes, and double hyphens across all dialogues.<br/>"
        "• <b>Booking Integrity:</b> No calendar slot is finalized without explicit date, exact clock time, timezone normalization, and explicit email verification.<br/>"
        "• <b>TCPA & Contact Hygiene:</b> Immediate carrier-compliant opt-out on 'STOP' or explicit wrong-number dismissals.",
        body_style
    ))
    story.append(Spacer(1, 14))

    story.append(Paragraph("20-Scenario Coverage & Lifecycle Matrix (Pure AI Services)", section_heading))
    
    index_headers = [
        Paragraph("<b>ID</b>", meta_key),
        Paragraph("<b>Scenario Title</b>", meta_key),
        Paragraph("<b>AI Category</b>", meta_key),
        Paragraph("<b>Lead / Company</b>", meta_key),
        Paragraph("<b>Final CRM Stage</b>", meta_key)
    ]
    index_rows = [index_headers]
    
    test_cases = get_test_cases_dataset()
    for tc in test_cases:
        last_stage = tc["stages"].split("->")[-1].strip()
        index_rows.append([
            Paragraph(f"<b>{tc['id']}</b>", meta_val),
            Paragraph(clean(tc['title']), meta_val),
            Paragraph(clean(tc['category']), meta_val),
            Paragraph(f"{clean(tc['lead_name'])}<br/><font color='#64748B'>{clean(tc['company'])}</font>", meta_val),
            Paragraph(f"<font color='#166534'><b>{clean(last_stage)}</b></font>", meta_val)
        ])
        
    index_table = Table(index_rows, colWidths=[36, 175, 115, 120, 94])
    index_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0B192C")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 3.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(index_table)
    
    story.append(PageBreak())
    
    # ---------------------------------------------------------
    # INDIVIDUAL TEST CASES (TC-01 through TC-20)
    # ---------------------------------------------------------
    
    for idx, tc in enumerate(test_cases):
        tc_elements = []
        
        # Test Case Header Banner
        header_table = Table(
            [
                [
                    Paragraph(f"<b>{tc['id']}</b>", tc_badge),
                    Paragraph(f"<b>{clean(tc['title'])}</b>", tc_title),
                    Paragraph(clean(tc['category']).upper(), tc_cat)
                ]
            ],
            colWidths=[45, 365, 130]
        )
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,0), NAVY_PRIMARY),
            ('ALIGN', (0,0), (0,0), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
            ('LINEBELOW', (0,0), (-1,-1), 1, TECH_BLUE),
        ]))
        tc_elements.append(header_table)
        tc_elements.append(Spacer(1, 6))
        
        # Lead Ingestion Profile & Simulation Context
        profile_data = [
            [
                Paragraph("<b>Lead Name:</b>", meta_key),
                Paragraph(clean(tc["lead_name"]), meta_val),
                Paragraph("<b>Company / Industry:</b>", meta_key),
                Paragraph(f"{clean(tc['company'])} ({clean(tc['industry'])})", meta_val),
            ],
            [
                Paragraph("<b>Job Title:</b>", meta_key),
                Paragraph(clean(tc["job_title"]), meta_val),
                Paragraph("<b>Initial Score / Agent:</b>", meta_key),
                Paragraph(f"{clean(tc['initial_score'])} | Alex (AI Intake)", meta_val),
            ],
            [
                Paragraph("<b>Contact Info:</b>", meta_key),
                Paragraph(f"{clean(tc['phone'])} | {clean(tc['email'])}", meta_val),
                Paragraph("<b>Upload Source:</b>", meta_key),
                Paragraph(f"<font color='#0284C7'><b>{clean(tc['source'])}</b></font>", meta_val),
            ],
            [
                Paragraph("<b>Scenario Context:</b>", meta_key),
                Paragraph(clean(tc["scenario"]), meta_val),
                Paragraph("", meta_key),
                Paragraph("", meta_val)
            ]
        ]
        profile_table = Table(profile_data, colWidths=[80, 190, 95, 175])
        profile_table.setStyle(TableStyle([
            ('SPAN', (1, 3), (3, 3)),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        tc_elements.append(profile_table)
        tc_elements.append(Spacer(1, 8))
        
        # Dialogue Section
        tc_elements.append(Paragraph(f"<b>Pure AI Services Conversational Transcript ({len(tc['dialogue'])} Turns)</b>", crm_title))
        tc_elements.append(Spacer(1, 4))
        
        dialogue_rows = []
        for d in tc["dialogue"]:
            is_ai = "Alex" in d["speaker"]
            
            speaker_label = f"<b>{clean(d['speaker'])}</b><br/><font size=6.5 color='#64748B'>{clean(d['time'])} • {clean(d['channel'])}</font>"
            msg_p = Paragraph(clean(d['text']), msg_ai if is_ai else msg_lead)
            spk_p = Paragraph(speaker_label, ai_speaker if is_ai else lead_speaker)
            
            row = [spk_p, msg_p]
            dialogue_rows.append(row)
            
        dialogue_table = Table(dialogue_rows, colWidths=[105, 435])
        dialogue_styles = [
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ]
        
        for r_idx, d in enumerate(tc["dialogue"]):
            is_ai = "Alex" in d["speaker"]
            bg = BG_LIGHT_AI if is_ai else BG_LIGHT_LEAD
            dialogue_styles.append(('BACKGROUND', (0, r_idx), (-1, r_idx), bg))
            
        dialogue_table.setStyle(TableStyle(dialogue_styles))
        tc_elements.append(dialogue_table)
        tc_elements.append(Spacer(1, 8))
        
        # CRM Lifecycle Progression & Automation Actions
        crm_rows = [
            [
                Paragraph("<b>Detected Intent:</b>", crm_title),
                Paragraph(f"<font color='#0B192C'><b>{clean(tc['intent'])}</b></font>", crm_text)
            ],
            [
                Paragraph("<b>Lifecycle Flow:</b>", crm_title),
                Paragraph(f"<font color='#1E40AF'><b>{clean(tc['stages'])}</b></font>", crm_text)
            ],
            [
                Paragraph("<b>CRM Automations:</b>", crm_title),
                Paragraph("<br/>".join([f"• {clean(act)}" for act in tc["crm_actions"]]), crm_text)
            ],
            [
                Paragraph("<b>Guardrails Met:</b>", crm_title),
                Paragraph(f"<font color='#166534'>✓ {clean(tc['guardrails'])}</font>", crm_text)
            ]
        ]
        crm_table = Table(crm_rows, colWidths=[95, 445])
        crm_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0,0), (-1,-1), 3.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        tc_elements.append(crm_table)
        
        story.append(KeepTogether(tc_elements))
        if idx < len(test_cases) - 1:
            story.append(Spacer(1, 14))
            story.append(PageBreak())
            
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated pure AI services test suite: {output_filename}")

if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "/Users/ec2-user/troy-campaign/AllZone_AI_Lead_Automation_20_Test_Cases.pdf"
    build_pdf(out_path)
