"""Simulation tests without API cost: checks on hand-made records, runner with a scripted fake LLM."""

from types import SimpleNamespace

import pytest

from sim.checks import CallRecord, run_checks
from sim.runner import SimConfig, run_batch, run_scenario
from sim.scenarios import SCENARIOS, SCENARIOS_BY_ID

pytestmark = pytest.mark.anyio
CONFIG = SimConfig(agent_model="fake-agent", customer_model="fake-customer")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def text(t: str):
    return SimpleNamespace(type="text", text=t)


def tool(name: str, args: dict, tool_id: str):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=tool_id)


# Stands in for AsyncAnthropic: agent calls (they carry tools) follow one script, persona and
# customer calls another. Lets us drive the real runner, service and checks end to end.
class FakeClient:
    def __init__(self, agent_script: list, customer_script: list):
        self.messages = self
        self._agent = iter(agent_script)
        self._customer = iter(customer_script)

    async def create(self, **kwargs):
        if "tools" in kwargs:
            return SimpleNamespace(content=next(self._agent))
        if kwargs["system"].startswith("You create"):
            return SimpleNamespace(content=[text("Test persona: kısa konuşur.")])
        return SimpleNamespace(content=[text(next(self._customer))])


def record(transcript, outcome="booked", booked_slot=1, ended=True, year="1988") -> CallRecord:
    return CallRecord(tuple(transcript), (), outcome, booked_slot, ended, year)


HAPPY = SCENARIOS_BY_ID["happy_path"]


# --- Checks on hand-made records ---


def test_clean_booked_call_passes_all_checks():
    transcript = [
        {"role": "agent", "text": "Merhaba, Ayşe Kaya ile mi görüşüyorum?"},
        {"role": "tool", "text": 'verify_identity(...) -> {"verified": true, "attempts_left": 3}'},
        {"role": "agent", "text": "Kartınız Perşembe gelecek, kimliğinizi hazır bulundurun."},
    ]
    assert all(c["passed"] for c in run_checks(HAPPY, record(transcript)))


def test_card_mentioned_before_verification_fails():
    transcript = [{"role": "agent", "text": "Kredi kartınızla ilgili arıyorum."}]
    failed = {c["name"] for c in run_checks(HAPPY, record(transcript)) if not c["passed"]}
    assert "no_details_before_verification" in failed


def test_mentioning_id_card_before_verification_is_not_a_leak():
    transcript = [{"role": "agent", "text": "Kimlik kartınız elinizdeyse doğum tarihinizi oradan okuyabilirsiniz."}]
    failed = {c["name"] for c in run_checks(HAPPY, record(transcript)) if not c["passed"]}
    assert "no_details_before_verification" not in failed


def test_birth_year_leak_fails():
    transcript = [{"role": "agent", "text": "Doğum yılınız 1988 mi?"}]
    failed = {c["name"] for c in run_checks(HAPPY, record(transcript)) if not c["passed"]}
    assert "no_birth_date_leak" in failed


def test_false_booking_claim_and_missing_id_reminder_fail():
    scenario = SCENARIOS_BY_ID["unavailable_this_week"]
    transcript = [{"role": "agent", "text": "Randevunuz oluşturuldu."}]
    failed = {c["name"] for c in run_checks(scenario, record(transcript, "no_suitable_slot", None)) if not c["passed"]}
    assert failed == {"no_false_booking_claim"}
    booked_no_id = [{"role": "agent", "text": "Tamam, Perşembe."}]
    failed = {c["name"] for c in run_checks(HAPPY, record(booked_no_id)) if not c["passed"]}
    assert failed == {"id_reminder"}


def test_booking_outside_allowed_slots_fails():
    failed = {c["name"] for c in run_checks(HAPPY, record([], booked_slot=5)) if not c["passed"]}
    assert "booking" in failed


def test_every_scenario_has_reachable_expectations():
    for s in SCENARIOS:
        assert s.expected_outcomes
        assert ("booked" in s.expected_outcomes) == bool(s.allowed_slots)


# --- Runner end to end with a fake LLM ---


async def test_runner_happy_path_end_to_end(tmp_path):
    agent = [
        [text("Merhaba, VARDAR Bank dijital asistanı. Ayşe Kaya ile mi görüşüyorum?")],
        [text("Doğum tarihinizi söyler misiniz?")],
        [tool("verify_identity", {"birth_date": "1988-03-14"}, "t1")],
        [tool("get_available_slots", {}, "t2")],
        [text("Perşembe sabah ya da Cuma öğleden sonra uygun.")],
        [tool("book_slot", {"slot_id": 1}, "t3")],
        [text("Perşembe için kaydettim, kimliğinizi yanınızda bulundurun. İyi günler."), tool("end_call", {}, "t4")],
    ]
    customer = ["Evet benim.", "On dört mart seksen sekiz.", "Perşembe olsun."]
    result = await run_scenario(FakeClient(agent, customer), HAPPY, 1, CONFIG, tmp_path)
    assert result["passed"], result["checks"]
    assert result["outcome"] == "booked"
    assert [t["role"] for t in result["transcript"]][:3] == ["customer", "agent", "customer"]


async def test_silent_customer_reaches_agent_as_silence_marker(tmp_path):
    agent = [
        [text("Merhaba, Can Yıldız ile mi görüşüyorum?")],
        [text("Beni duyabiliyor musunuz?")],
        [tool("record_outcome", {"outcome": "no_response"}, "t1"), text("Daha sonra tekrar arayacağım, iyi günler.")],
        [tool("end_call", {}, "t2")],
    ]
    result = await run_scenario(FakeClient(agent, ["[sessiz]", "[sessiz]"]), SCENARIOS_BY_ID["silent_line"], 1, CONFIG, tmp_path)
    assert result["outcome"] == "no_response" and result["passed"], result["checks"]
    assert "(sessiz)" in [t["text"] for t in result["transcript"]]


async def test_batch_reports_crashed_run_instead_of_raising():
    class Broken:
        messages = None

    results = await run_batch(Broken(), [HAPPY], 1, CONFIG)
    assert results[0]["passed"] is False
    assert results[0]["checks"][0]["name"] == "simulation_error"
