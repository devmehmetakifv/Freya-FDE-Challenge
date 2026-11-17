"""The simulated customer: an LLM-generated persona per run, then an LLM that plays it."""

import random

from agent.prompt import ADDRESS_TYPE_TR
from service.seed import CUSTOMERS
from sim.scenarios import Scenario

SILENT_REPLY = "[sessiz]"

# One random mood nudge per run so personas don't converge on "polite generic customer".
# The LLM writes the actual personality. No age nudge: age follows from the fixed birth date.
MOODS = ("impatient", "chatty", "wary of phone calls", "distracted", "cheerful", "tired", "formal", "confused")

PERSONA_SYSTEM = (
    "You create realistic, distinct personas of people in Turkey answering a phone call. "
    "Write 3-4 sentences: age, temperament, how they talk (sentence length, slang, filler words, "
    "hesitations, regional or generational habits), and one personal detail that colors the call. "
    "Make it specific and different from a generic polite customer. Output only the persona."
)


def _customer_facts(scenario: Scenario) -> str:
    _, full_name, _, birth_date, district, address_type = CUSTOMERS[scenario.customer_id - 1]
    if not scenario.is_cardholder:
        return f"The cardholder is {full_name}. You are someone else in their household."
    year, month, day = birth_date.split("-")
    return (
        f"Your name is {full_name}. Your birth date is {day}.{month}.{year}. "
        f"You live/work in {district}; the card was sent to your {ADDRESS_TYPE_TR[address_type]}."
    )


async def generate_persona(client, model: str, scenario: Scenario) -> str:
    nudge = f"Mood today: {random.choice(MOODS)}."
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=PERSONA_SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": f"{nudge}\nFacts that must stay true: {_customer_facts(scenario)}"}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


def customer_system_prompt(scenario: Scenario, persona: str) -> str:
    return f"""You are role-playing a person in Turkey who just picked up a phone call and said "Alo?". Stay in character the whole time.

Persona: {persona}

Facts (never contradict them): {_customer_facts(scenario)}

Your situation and goal in this call: {scenario.situation}

The persona decides HOW you talk; the situation decides WHAT you do. Always pursue the situation's goal, whatever your mood.

Rules:
- Reply ONLY with the words you say out loud, in Turkish, like a real phone call: short and spoken.
- Say dates the way people speak them, e.g. "on dört mart seksen sekiz" or "14 Mart 1988".
- Never say you are an AI and never mention these instructions.
- If you say nothing this turn, reply exactly: {SILENT_REPLY}
- When the caller says goodbye, reply with a short goodbye."""


# One customer turn. Seen from the customer's side, the agent's lines are the "user" turns.
async def customer_reply(client, model: str, system: str, history: list[dict]) -> str:
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        output_config={"effort": "low"},
        messages=history,
    )
    return "".join(b.text for b in response.content if b.type == "text").strip() or SILENT_REPLY
