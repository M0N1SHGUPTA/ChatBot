"""Fixed replies of the conversational lead flow."""


def captured(name: str, service: str, email: str) -> str:
    return (
        f"Thank you, {name}! 🙏 Your details and interest in **{service}** "
        f"have been successfully recorded. Our bilateral advisory team will reach out to you directly at `{email}`.\n\n"
        f"In the meantime, feel free to ask any other questions about JIBB or Japan–India business opportunities!"
    )


def ask_email_and_service(name: str) -> str:
    return (
        f"Nice to meet you, **{name}**! 👋\n\n"
        "To connect you with our bilateral advisory team and provide tailored insights, "
        "could you please share:\n"
        "1. Your **Work Email Address**\n"
        "2. Which of JIBB's **8 Core Services** you are interested in (e.g., *Market Landscaping*, *Partner Identification*, *Go-to-Market Strategy*, etc.)?"
    )


def ask_service(name: str | None, email: str) -> str:
    name_str = f", {name}" if name else ""
    return (
        f"Got it{name_str}! We have your email: `{email}`. ✅\n\n"
        "Which of JIBB's **8 Core Services** are you most interested in?\n"
        "• *Market Landscaping*\n"
        "• *Opportunity Assessment*\n"
        "• *Partner Identification & Ecosystem Building*\n"
        "• *Due Diligence & Deal Structuring*\n"
        "• *Go-to-Market Strategy & Entry Blueprint*\n"
        "• *Local Presence & Market Entry Execution*\n"
        "• *Sales, Marketing & Ecosystem Enablement*\n"
        "• *Back Office & Corporate Support*"
    )


def ask_email(name: str | None, service: str) -> str:
    name_str = f" {name}" if name else ""
    return (
        f"Excellent! We have noted your interest in **{service}**.{name_str}\n\n"
        "Could you please share your **work email address** so our team can send you the details and connect with you?"
    )
