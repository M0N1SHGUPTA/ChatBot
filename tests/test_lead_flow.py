import pytest

from app.chat.sessions import SessionStore
from app.leads.flow import LeadFlow, extract_lead_fields
from app.leads.store import LeadStore


@pytest.fixture
def flow(tmp_path):
    return LeadFlow(LeadStore(tmp_path / "l.db", tmp_path / "l.json"), SessionStore(), trigger_turn=2)


def _activate(flow, sid, turns=2):
    for _ in range(turns):
        flow.sessions.increment_turns(sid)


def test_submit_normalises_and_stores(flow):
    lead = flow.submit("s", " Alice ", " Alice@Company.com ", "Market Landscaping", " expansion ")
    assert (lead.name, lead.email, lead.notes) == ("Alice", "alice@company.com", "expansion")
    assert [l.email for l in flow.all_leads()] == ["alice@company.com"]


def test_trigger_threshold(flow):
    assert not flow.is_active("s")
    _activate(flow, "s", 1)
    assert not flow.is_active("s")
    _activate(flow, "s", 1)
    assert flow.is_active("s")
    flow.submit("s", "A", "a@b.com", "Market Landscaping")
    assert not flow.is_active("s")


def test_conversational_flow(flow):
    _activate(flow, "s")
    r1 = flow.process("s", "My name is Monish Gupta")
    assert r1 and not r1.is_complete and "Monish Gupta" in r1.answer
    r2 = flow.process("s", "monish@example.com")
    assert r2 and not r2.is_complete and "monish@example.com" in r2.answer
    r3 = flow.process("s", "Market Landscaping")
    assert r3 and r3.is_complete and "successfully recorded" in r3.answer
    assert r3.lead.email == "monish@example.com"


def test_inactive_before_trigger_turn(flow):
    _activate(flow, "s", 1)
    assert flow.process("s", "Tell me about Market Landscaping please") is None
    assert flow.process("s", "My name is Bob Smith") is None


@pytest.mark.parametrize("text", [
    "ok", "no thanks", "No thanks, I don't want to share my details.",
    "Membership tiers", "会員プラン", "東京オフィスはどこですか？",
    "I am interested in membership.", "I'm looking for partners in India", "This is helpful",
])
def test_non_lead_messages_go_to_rag(flow, text):
    _activate(flow, "s")
    assert flow.process("s", text) is None


def test_question_after_partial_draft_goes_to_rag(flow):
    _activate(flow, "s")
    assert flow.process("s", "My name is Arjun Mehta") is not None
    assert flow.process("s", "Wait, where exactly is your Noida office?") is None
    r = flow.process("s", "arjun.mehta@example.com")
    assert r is not None and "Arjun Mehta" in r.answer


def test_email_trailing_punctuation_stripped():
    assert extract_lead_fields("My email is bob@acme.com.")["email"] == "bob@acme.com"
    assert "email" not in extract_lead_fields("my email is sara.ito@example")


def test_name_and_email_in_one_message():
    f = extract_lead_fields("Sure, I'm Kenji Tanaka, kenji.tanaka@example.co.jp, thanks")
    assert f == {"name": "Kenji Tanaka", "email": "kenji.tanaka@example.co.jp"}
