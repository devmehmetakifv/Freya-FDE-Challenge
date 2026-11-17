"""Agent tools: one definition list and one executor, shared by the voice bot and the simulator."""

from dataclasses import dataclass, field

import httpx

# Outcomes the agent may record; mirrors service.bank.AGENT_OUTCOMES (the service validates).
OUTCOMES = [
    "no_suitable_slot",
    "wrong_person",
    "verification_failed",
    "callback_requested",
    "declined",
    "needs_human",
    "no_response",
]

# Tool definitions in a neutral shape (name, description, JSON-schema properties, required).
# The call_id is never a tool argument: the session holds it, so the LLM can't touch another call.
TOOL_SPECS = [
    {
        "name": "verify_identity",
        "description": "Check the customer's birth date against the bank record. "
        "Returns verified and attempts_left. Required before any delivery detail.",
        "properties": {
            "birth_date": {"type": "string", "description": "Birth date as YYYY-MM-DD"},
        },
        "required": ["birth_date"],
    },
    {
        "name": "get_available_slots",
        "description": "List this week's free courier slots in the customer's district. "
        "Only works after verify_identity succeeded.",
        "properties": {},
        "required": [],
    },
    {
        "name": "book_slot",
        "description": "Book a courier slot for the customer. Booking again moves the existing booking.",
        "properties": {
            "slot_id": {"type": "integer", "description": "slot_id from get_available_slots"},
        },
        "required": ["slot_id"],
    },
    {
        "name": "record_outcome",
        "description": "Record how the call ended when no slot was booked.",
        "properties": {
            "outcome": {"type": "string", "enum": OUTCOMES},
            "note": {"type": "string", "description": "Short note, e.g. the customer's preferred times"},
        },
        "required": ["outcome"],
    },
    {
        "name": "end_call",
        "description": "Hang up. Call this only after you have said goodbye.",
        "properties": {},
        "required": [],
    },
]


# Anthropic Messages API shape, used by the simulator.
def anthropic_tools() -> list[dict]:
    return [
        {
            "name": spec["name"],
            "description": spec["description"],
            "input_schema": {
                "type": "object",
                "properties": spec["properties"],
                "required": spec["required"],
            },
        }
        for spec in TOOL_SPECS
    ]


# One call's state against the slot service. Every tool result is a plain dict; service errors
# come back as {"error": ..., "message": ...} so the LLM can react instead of crashing the call.
@dataclass
class CallSession:
    http: httpx.AsyncClient
    call_id: int
    customer: dict
    ended: bool = False
    tool_log: list[dict] = field(default_factory=list)

    # Opens the call on the service and returns a session bound to it.
    @classmethod
    async def open(cls, http: httpx.AsyncClient, customer_id: int) -> "CallSession":
        resp = await http.post("/calls", json={"customer_id": customer_id})
        resp.raise_for_status()
        body = resp.json()
        return cls(http=http, call_id=body["call_id"], customer=body["customer"])

    async def execute(self, name: str, args: dict) -> dict:
        result = await self._dispatch(name, args)
        self.tool_log.append({"tool": name, "args": args, "result": result})
        return result

    async def _dispatch(self, name: str, args: dict) -> dict:
        base = f"/calls/{self.call_id}"
        try:
            if name == "verify_identity":
                return await self._send("POST", f"{base}/verify", {"birth_date": args.get("birth_date")})
            if name == "get_available_slots":
                return {"slots": await self._send("GET", f"{base}/slots")}
            if name == "book_slot":
                return await self._send("POST", f"{base}/book", {"slot_id": args.get("slot_id")})
            if name == "record_outcome":
                payload = {"outcome": args.get("outcome"), "note": args.get("note", "")}
                return await self._send("POST", f"{base}/outcome", payload)
            if name == "end_call":
                self.ended = True
                return {"ended": True}
            return {"error": "unknown_tool", "message": f"no tool named {name}"}
        except (httpx.HTTPError, ValueError) as exc:
            # Network trouble or a non-JSON reply: tell the LLM plainly so it can apologize
            # instead of inventing a result.
            return {"error": "service_unavailable", "message": str(exc)}

    # Service error bodies are already {"error", "message"}; 422 (bad input, e.g. a malformed
    # date) is replaced with a message the LLM can act on.
    async def _send(self, method: str, path: str, payload: dict | None = None):
        resp = await self.http.request(method, path, json=payload)
        if resp.status_code == 422:
            return {"error": "invalid_input", "message": "input format is invalid, ask the customer again"}
        return resp.json()
