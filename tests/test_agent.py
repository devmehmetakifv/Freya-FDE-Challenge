"""Agent core tests: the tool executor against a real in-process slot service, and prompt safety."""

import httpx
import pytest

from agent.prompt import build_system_prompt
from agent.tools import OUTCOMES, TOOL_SPECS, CallSession, anthropic_tools
from service.app import create_app
from service.bank import AGENT_OUTCOMES

pytestmark = pytest.mark.anyio

AYSE, AYSE_DOB, KADIKOY_THU = 1, "1988-03-14", 1


@pytest.fixture
def anyio_backend():
    return "asyncio"


# The service runs in-process on a throwaway DB; httpx talks to it without opening a port.
@pytest.fixture
async def http(tmp_path):
    transport = httpx.ASGITransport(app=create_app(tmp_path / "bank.db"))
    async with httpx.AsyncClient(transport=transport, base_url="http://bank") as client:
        yield client


async def test_happy_path_verify_list_book(http):
    session = await CallSession.open(http, AYSE)
    assert (await session.execute("verify_identity", {"birth_date": AYSE_DOB}))["verified"]
    slots = (await session.execute("get_available_slots", {}))["slots"]
    assert [s["slot_id"] for s in slots] == [1, 2]
    booked = await session.execute("book_slot", {"slot_id": KADIKOY_THU})
    assert booked["booked"] and booked["slot"]["day"] == "Perşembe"
    assert [entry["tool"] for entry in session.tool_log] == ["verify_identity", "get_available_slots", "book_slot"]


# Service refusals come back as data the LLM can read, never as exceptions that kill the call.
async def test_service_errors_become_error_dicts(http):
    session = await CallSession.open(http, AYSE)
    assert (await session.execute("book_slot", {"slot_id": KADIKOY_THU}))["error"] == "not_verified"
    assert (await session.execute("verify_identity", {"birth_date": "14 Mart"}))["error"] == "invalid_input"
    assert (await session.execute("teleport", {}))["error"] == "unknown_tool"


async def test_service_down_is_reported_not_raised():
    transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("down")))
    async with httpx.AsyncClient(transport=transport, base_url="http://bank") as client:
        session = CallSession(http=client, call_id=1, customer={})
        result = await session.execute("get_available_slots", {})
    assert result["error"] == "service_unavailable"


async def test_end_call_marks_session_ended(http):
    session = await CallSession.open(http, AYSE)
    assert await session.execute("end_call", {}) == {"ended": True}
    assert session.ended


async def test_every_agent_outcome_is_accepted_by_service(http):
    for outcome in OUTCOMES:
        session = await CallSession.open(http, AYSE)
        result = await session.execute("record_outcome", {"outcome": outcome, "note": "test"})
        assert result == {"call_id": session.call_id, "outcome": outcome}


def test_agent_outcomes_mirror_service():
    assert tuple(OUTCOMES) == AGENT_OUTCOMES


def test_anthropic_tool_shape_matches_specs():
    tools = anthropic_tools()
    assert [t["name"] for t in tools] == [s["name"] for s in TOOL_SPECS]
    assert all(t["input_schema"]["type"] == "object" for t in tools)


def test_prompt_has_customer_context_and_no_pii():
    prompt = build_system_prompt({"full_name": "Ayşe Kaya", "district": "Kadıköy", "address_type": "home"})
    assert "Ayşe Kaya" in prompt and "Kadıköy" in prompt and "ev adresi" in prompt
    assert "VARDAR Bank" in prompt
    assert "1988" not in prompt and "0532" not in prompt
    assert "daha önce görüşme yapılmadı" in prompt


def test_prompt_includes_previous_call_notes():
    customer = {"full_name": "Ayşe Kaya", "district": "Kadıköy", "address_type": "home"}
    previous = [{"started_at": "2026-11-17T14:42:00+00:00", "outcome": "no_suitable_slot", "note": "Pazar gece 23:30"}]
    prompt = build_system_prompt(customer, previous)
    assert "no_suitable_slot" in prompt and "Pazar gece 23:30" in prompt


async def test_session_carries_previous_calls(http):
    first = await CallSession.open(http, AYSE)
    await first.execute("record_outcome", {"outcome": "callback_requested", "note": "akşam ara"})
    second = await CallSession.open(http, AYSE)
    assert second.previous_calls[0]["note"] == "akşam ara"
