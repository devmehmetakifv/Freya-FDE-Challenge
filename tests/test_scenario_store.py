"""Editable scenarios: the JSON store, its validation, and the sim server's CRUD endpoints."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sim import server
from sim.scenarios import SCENARIOS
from sim.store import (
    ScenarioExists,
    ScenarioModel,
    ScenarioNotFound,
    ScenarioStore,
    scenario_to_dict,
)

NEW = {
    "id": "weekend_only",
    "title": "Weekend only",
    "description": "Customer can only do the weekend.",
    "customer_id": 4,
    "situation": "You are the cardholder and only free on Sunday.",
    "expected_outcomes": ["no_suitable_slot"],
    "allowed_slots": [],
    "setup_bookings": [],
    "is_cardholder": True,
}


@pytest.fixture
def store(tmp_path):
    return ScenarioStore(tmp_path / "sim.db")


# A fresh store per test, swapped into the server module so the API uses it too.
@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(server, "STORE", store)
    return TestClient(server.app)


# --- Store ---


def test_new_db_is_seeded_once_and_deletions_stick(store):
    assert [s.id for s in store.list()] == [s.id for s in SCENARIOS]
    store.delete("happy_path")
    assert "happy_path" not in [s.id for s in ScenarioStore(store.path).list()]


def test_create_update_delete_persist_across_reloads(store):
    store.create(ScenarioModel(**NEW).to_scenario())
    edited = ScenarioModel(**{**NEW, "title": "Sunday only"}).to_scenario()
    store.update("weekend_only", edited)
    reloaded = ScenarioStore(store.path)
    assert reloaded.get("weekend_only").title == "Sunday only"
    assert [s.id for s in reloaded.list()][-1] == "weekend_only"  # appended at the end
    reloaded.delete("weekend_only")
    with pytest.raises(ScenarioNotFound):
        ScenarioStore(store.path).get("weekend_only")


def test_duplicate_id_is_rejected(store):
    with pytest.raises(ScenarioExists):
        store.create(ScenarioModel(**{**NEW, "id": "happy_path"}).to_scenario())


def test_round_trip_keeps_every_field(store):
    original = next(s for s in SCENARIOS if s.setup_bookings)
    assert ScenarioModel.model_validate(scenario_to_dict(original)).to_scenario() == original


@pytest.mark.parametrize(
    "change",
    [
        {"id": "Bad Id!"},
        {"customer_id": 99},
        {"expected_outcomes": []},
        {"expected_outcomes": ["teleported"]},
        {"expected_outcomes": ["booked"]},  # booked without allowed slots
        {"allowed_slots": [1]},  # allowed slots without booked
        {"setup_bookings": [[1, 42]]},
        {"situation": "short"},
    ],
)
def test_invalid_scenarios_are_rejected(change):
    with pytest.raises(ValidationError):
        ScenarioModel(**{**NEW, **change})


# --- API ---


def test_api_crud_flow(client):
    assert client.post("/scenarios", json=NEW).status_code == 201
    assert client.post("/scenarios", json=NEW).status_code == 409
    assert client.put("/scenarios/weekend_only", json={**NEW, "title": "Edited"}).json()["title"] == "Edited"
    assert client.put("/scenarios/weekend_only", json={**NEW, "id": "renamed"}).status_code == 422
    assert client.delete("/scenarios/weekend_only").status_code == 204
    assert client.delete("/scenarios/weekend_only").status_code == 404
    assert "weekend_only" not in [s["id"] for s in client.get("/scenarios").json()]


def test_api_rejects_invalid_scenario(client):
    assert client.post("/scenarios", json={**NEW, "expected_outcomes": ["booked"]}).status_code == 422


def test_meta_lists_form_options(client):
    meta = client.get("/meta").json()
    assert "booked" in meta["outcomes"] and "no_response" in meta["outcomes"]
    assert len(meta["customers"]) == 8 and len(meta["slots"]) == 5


def test_run_with_deleted_scenario_is_rejected(client):
    client.delete("/scenarios/happy_path")
    resp = client.post("/runs", json={"scenario_ids": ["happy_path"], "runs_per_scenario": 1})
    assert resp.status_code == 422
