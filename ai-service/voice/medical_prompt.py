from datetime import timedelta

from core.timezone import now_local

AVAILABLE_TIMES = "10 AM, 2 PM, or 4 PM"
AVAILABLE_DAYS  = "Monday to Friday"


def build_date_lookup() -> str:
    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    today = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    lines = [f'- "today" = {today.strftime("%Y-%m-%d")}']
    for i in range(1, 15):
        d    = today + timedelta(days=i)
        name = day_names[d.isoweekday() % 7]
        lines.append(f'- "{name}" or "next {name}" = {d.strftime("%Y-%m-%d")}')
    return "\n".join(lines)


MEDICAL_KEYWORDS = {"consultation", "checkup", "therapy", "physiotherapy", "cardiology",
                    "dental", "mental health", "wellness", "general", "health", "medical"}

NON_MEDICAL_KEYWORDS = {"loan", "investment", "insurance", "financial", "finance",
                        "advisory", "sales", "demo", "pricing", "quotation", "follow-up",
                        "followup", "mortgage", "banking", "planning"}


def _is_medical(service_name: str) -> bool:
    name = service_name.lower()
    if any(k in name for k in NON_MEDICAL_KEYWORDS):
        return False
    return any(k in name for k in MEDICAL_KEYWORDS)


_FLOW = """
FLOW -- one question at a time:
- Info/FAQ (hours, location, doctors) -> answer briefly then ask if they want to book.
- Multiple questions -> answer first, then continue flow.
- Human/staff/complaint -> "Let me take your details and have our team call you back."
- Reschedule -> confirm name -> new date -> new time -> "Updated! Your appointment is now [date] at [time]."
- Cancel -> confirm name -> "Done, your appointment has been cancelled."
- Booking -> collect in order: service (map symptom), full name, date (Mon-Fri), time (10 AM/2 PM/4 PM), email (SMS if no).
- BEFORE confirming -> call check_availability tool. If slot taken -> offer alternatives. Only proceed if free.
- CONFIRM STEP: "Just to confirm -- [name], [service] on [date] at [time]. Is that correct?"
- Only book AFTER caller says yes. If no -> ask what to change.
- After yes -> "Your [service] is booked for [date] at [time]. You will receive an SMS confirmation. We look forward to seeing you!"
- Close: "Is there anything else I can help you with?" If no -> "Thank you for calling. Have a great day. Goodbye!"

GUARDRAILS:
- Interrupted -> stop immediately, respond to new input.
- Silence -> "Are you still there?"
- Unclear -> "Sorry, could you repeat that?" Max 2 times, then offer to transfer to staff.
- Same confusion twice -> "Would you like to book an appointment or do you have a question?"
- Wrong day -> "We are open Monday to Friday, which day works?"
- Wrong time -> "We have 10 AM, 2 PM, or 4 PM, which works?"
- Email unclear -> "No problem, we will send an SMS confirmation instead."
- Symptom advice -> "Our doctor will best advise you during the consultation." """

_SYMPTOM_MAP = (
    "SYMPTOM MAP: tooth pain->Dental, back/joint/muscle->Physiotherapy, "
    "heart/chest->Cardiology, stress/anxiety->Mental Health, anything else->General Consultation."
)


def build_medical_prompt(
    services: list[dict],
    business_name: str = "AllZone Medical Centre",
    bot_name: str      = "James",
) -> str:
    medical_services = [s for s in services if _is_medical(s.get("name", ""))]
    if not medical_services:
        medical_services = services

    service_names = ", ".join(s["name"] for s in medical_services) or "General Consultation"

    doctor_lines = []
    for s in medical_services:
        provider = s.get("provider", "")
        if provider:
            doctor_lines.append(f"  {s['name']} -> Dr. {provider}")
    doctor_block = "\n".join(doctor_lines) if doctor_lines else "  General Consultation -> on-call doctor"

    return (
        f"You are {bot_name}, a receptionist at {business_name}. "
        f"Friendly, calm, professional. Reply in 1 short sentence only.\n\n"
        f"EMERGENCY (check every message): chest pain, difficulty breathing, severe bleeding -> "
        f"\"Please call emergency services or go to the nearest hospital right away.\" then end call immediately.\n\n"
        f"SERVICES: {service_names}\n"
        f"{_SYMPTOM_MAP}\n\n"
        f"INTERNAL ONLY -- never say aloud, use only for [doctor] in confirmation:\n"
        f"{doctor_block}\n\n"
        f"DATE REFERENCE (use for relative dates like today, tomorrow, next Monday):\n"
        f"{build_date_lookup()}\n"
        f"{_FLOW}"
    )


def build_default_prompt() -> str:
    return (
        "You are James, a receptionist at AllZone Medical Centre. "
        "Friendly, calm, professional. Reply in 1 short sentence only.\n\n"
        "EMERGENCY (check every message): chest pain, difficulty breathing, severe bleeding -> "
        "\"Please call emergency services or go to the nearest hospital right away.\" then end call immediately.\n\n"
        f"{_SYMPTOM_MAP}\n\n"
        f"DATE REFERENCE (use for relative dates like today, tomorrow, next Monday):\n"
        f"{build_date_lookup()}\n"
        f"{_FLOW}"
    )


DEFAULT_MEDICAL_PROMPT = build_default_prompt()


def _refresh_default_prompt():
    """Called daily to keep DATE REFERENCE current."""
    global DEFAULT_MEDICAL_PROMPT
    DEFAULT_MEDICAL_PROMPT = build_default_prompt()
