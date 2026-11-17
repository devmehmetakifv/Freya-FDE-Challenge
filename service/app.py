"""HTTP API of the slot service: the bank's system that the voice agent calls mid-conversation."""

import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from service import bank
from service.db import connect, init_db


class OpenCallRequest(BaseModel):
    customer_id: int


class VerifyRequest(BaseModel):
    # Pydantic rejects malformed dates with a 422 before they can burn a verification attempt.
    birth_date: date


class BookRequest(BaseModel):
    slot_id: int


class OutcomeRequest(BaseModel):
    outcome: Literal[bank.AGENT_OUTCOMES]  # type: ignore[valid-type]
    note: str = Field(default="", max_length=500)


# App factory so tests and the simulator can each run the service on their own throwaway DB.
def create_app(db_path: str | Path) -> FastAPI:
    init_db(db_path)
    app = FastAPI(title="Bank Slot Service")

    # A fresh connection per request; SQLite handles the locking between them.
    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[sqlite3.Connection, Depends(get_conn)]

    # Domain errors become a small, consistent JSON error the agent can reason about.
    @app.exception_handler(bank.BankError)
    async def bank_error_handler(_: Request, exc: bank.BankError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": str(exc)})

    # --- Call flow endpoints (used by the voice agent) ---

    @app.post("/calls")
    def open_call(body: OpenCallRequest, conn: Conn) -> dict:
        return bank.open_call(conn, body.customer_id)

    @app.post("/calls/{call_id}/verify")
    def verify(call_id: int, body: VerifyRequest, conn: Conn) -> dict:
        return bank.verify_identity(conn, call_id, body.birth_date)

    @app.get("/calls/{call_id}/slots")
    def slots_for_call(call_id: int, conn: Conn) -> list[dict]:
        return bank.available_slots(conn, call_id)

    @app.post("/calls/{call_id}/book")
    def book(call_id: int, body: BookRequest, conn: Conn) -> dict:
        return bank.book_slot(conn, call_id, body.slot_id)

    @app.post("/calls/{call_id}/outcome")
    def outcome(call_id: int, body: OutcomeRequest, conn: Conn) -> dict:
        return bank.record_outcome(conn, call_id, body.outcome, body.note)

    # --- Read endpoints (used by the bank panel) ---

    @app.get("/customers")
    def customers(conn: Conn) -> list[dict]:
        return bank.list_customers(conn)

    @app.get("/slots")
    def slots(conn: Conn) -> list[dict]:
        return bank.list_slots(conn)

    @app.get("/calls")
    def calls(conn: Conn) -> list[dict]:
        return bank.list_calls(conn)

    return app
