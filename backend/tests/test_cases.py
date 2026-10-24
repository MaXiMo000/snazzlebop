"""Reports as cases: versioned events through the outbox (at least once, retried, then failed and kept),
signed webhooks, the integration API (auth, reading, writing back triage and ticket links), and the
moderators' view of all of it."""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import update  # noqa: E402

from app import events, outbox  # noqa: E402
from app.db import OutboxItem  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.test_api import settings  # noqa: E402

PW = "correct horse battery"
TOKEN = "i" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeSink:
    name = "fake"

    def __init__(self) -> None:
        self.got: list[tuple[str, int, dict]] = []
        self.fail = False

    def deliver(self, topic: str, delivery_id: int, payload: dict) -> None:
        if self.fail:
            raise ConnectionError("down")
        self.got.append((topic, delivery_id, payload))


@pytest.fixture()
def client(tmp_path):
    app = create_app(
        settings(tmp_path, rate_auth_burst=1000, integration_token=TOKEN, public_url="https://snz.test")
    )
    with TestClient(app) as c:
        c.sink = FakeSink()
        app.state.outbox.sinks = {"fake": c.sink}
        yield c


def be(client, name):
    client.post("/api/auth/logout")
    if client.post("/api/auth/login", json={"username": name, "password": PW}).status_code != 200:
        assert client.post("/api/auth/signup", json={"username": name, "password": PW}).status_code == 201


def deliver(client) -> int:
    return client.portal.call(client.app.state.outbox.run_once)


def club_with_report(client, reason="hate"):
    be(client, "Ana_99")
    slug = client.post("/api/clubs", json={"name": "Hostel Four"}).json()["slug"]
    code = client.post(f"/api/clubs/{slug}/invites", json={}).json()["code"]
    for n in ("Bo_42", "Cy_77"):
        be(client, n)
        client.post("/api/clubs/join", json={"code": code})
    be(client, "Cy_77")
    r = client.post(
        "/api/reports", json={"username": "Bo_42", "reason": reason, "note": "rude", "club": slug}
    )
    assert r.json() == {"ok": True}
    return slug


def test_a_report_goes_out_as_a_versioned_event(client):
    slug = club_with_report(client)
    assert deliver(client) == 1
    [(topic, delivery, data)] = client.sink.got
    assert topic == "report.created" and delivery > 0
    assert data["v"] == 1 and data["id"].startswith("rpt_") and data["status"] == "open"
    assert data["priority"] == "high"  # hate starts high
    assert data["reason"] == "hate" and data["reason_label"] == "Hate or slurs" and data["note"] == "rude"
    assert data["reported"]["name"] == "Bo_42" and data["reported"]["ref"].startswith("usr_")
    assert data["reporter"] == {"ref": data["reporter"]["ref"]} and data["reporter"]["ref"].startswith("usr_")
    assert data["club"] == {"slug": slug, "name": "Hostel Four"}
    assert data["links"]["moderate"] == f"https://snz.test/clubs/{slug}/reports"
    assert data["event"] == {
        "kind": "created",
        "actor": "user:Cy_77",
        "data": {"reason": "hate", "room": None},
    }
    text = json.dumps(data)
    assert "Cy_77" not in text.replace('"user:Cy_77"', "")  # the reporter is only a pseudonym
    assert deliver(client) == 0  # delivered once, not again

    # A repeat report, then a moderator's decision: both go out as updates to the same case.
    client.post("/api/reports", json={"username": "Bo_42", "reason": "hate", "note": "again", "club": slug})
    be(client, "Ana_99")
    [row] = client.get(f"/api/clubs/{slug}/reports").json()["reports"]
    client.post(f"/api/clubs/{slug}/reports/{row['id']}", json={"action": "mute", "hours": 24})
    deliver(client)
    kinds = [(t, d["event"]["kind"], d["id"]) for t, _, d in client.sink.got[1:]]
    assert kinds == [("report.updated", "merged", data["id"]), ("report.updated", "action", data["id"])]
    assert client.sink.got[-1][2]["status"] == "actioned"


def test_failed_deliveries_retry_then_give_up_and_stay_visible(client):
    club_with_report(client)
    client.sink.fail = True
    box = client.app.state.outbox
    t = [datetime.now(UTC)]
    box.clock = lambda: t[0]
    db = client.app.state.db
    assert deliver(client) == 1
    [item] = client.portal.call(db.outbox_due, 10) or [None]
    assert item is None  # waiting for its retry time
    for _ in range(2, outbox.MAX_ATTEMPTS + 1):

        async def due_now() -> None:
            async with db.sessions() as s:
                await s.execute(update(OutboxItem).values(next_at=datetime.now(UTC) - timedelta(seconds=1)))
                await s.commit()

        client.portal.call(due_now)
        assert deliver(client) == 1
    assert client.get("/api/integrations/health", headers=AUTH).json() == {
        "pending": 0,
        "failed": 1,
        "sinks": ["fake"],
    }
    assert outbox.backoff(1) == timedelta(seconds=30) and outbox.backoff(20) == timedelta(hours=1)


def test_webhooks_are_signed(monkeypatch):
    sent = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b""

    def fake_urlopen(req, timeout):
        sent["req"] = req
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    secret = "s" * 40
    outbox.WebhookSink("https://hooks.example.test/in", secret).deliver("report.created", 7, {"v": 1})
    req = sent["req"]
    body = req.data
    assert json.loads(body) == {"id": 7, "topic": "report.created", "data": {"v": 1}}
    stamp = req.get_header("X-snazzlebop-timestamp")
    assert req.get_header("X-snazzlebop-signature") == events.sign(secret, stamp, body)
    assert (
        req.get_header("X-snazzlebop-event") == "report.created"
        and req.get_header("X-snazzlebop-delivery") == "7"
    )


def test_the_integration_api_reads_and_writes_back(client):
    slug = club_with_report(client)
    assert client.get("/api/integrations/reports").status_code == 401
    assert (
        client.get("/api/integrations/reports", headers={"Authorization": "Bearer nope"}).status_code == 401
    )
    [case] = client.get("/api/integrations/reports", headers=AUTH).json()["reports"]
    pid = case["id"]
    url = f"/api/integrations/reports/{pid}"

    # A model triages it and a ticket is opened elsewhere.
    triage = {"source": "ai-triage", "triage": {"label": "hate", "score": 0.93, "summary": "Slur in chat"}}
    r = client.post(url, json={**triage, "priority": "urgent", "status": "triaged"}, headers=AUTH)
    assert r.status_code == 200 and r.json()["report"]["status"] == "triaged"
    assert r.json()["report"]["triage"] == {
        "label": "hate",
        "score": 0.93,
        "summary": "Slur in chat",
        "by": "ai-triage",
    }
    jira = {
        "source": "jira",
        "external": {"jira": {"key": "SNZ-12", "url": "https://jira.example.test/SNZ-12"}},
    }
    r = client.post(url, json=jira, headers=AUTH)
    assert r.json()["report"]["external"] == {
        "jira": {"key": "SNZ-12", "url": "https://jira.example.test/SNZ-12"}
    }
    assert [e["actor"] for e in r.json()["timeline"]] == [
        "user:Cy_77",
        "integration:ai-triage",
        "integration:jira",
    ]
    deliver(client)
    updates = [d for t, _, d in client.sink.got if t == "report.updated"]
    assert [u["event"]["data"]["source"] for u in updates] == [
        "ai-triage",
        "jira",
    ]  # receivers skip their echoes

    for bad in (
        {"source": "x", "status": "actioned"},  # only people act
        {"source": "x", "priority": "asap"},
        {"source": "x", "external": {"jira": {"key": "A", "url": "http://plain.test"}}},
        {"source": "X Y", "note": "hi"},
        {"source": "x"},
        {"source": "x", "triage": {"label": "a", "score": 2.0}},
    ):
        assert client.post(url, json=bad, headers=AUTH).status_code in (400, 422), bad
    assert client.get("/api/integrations/reports/rpt_nope", headers=AUTH).status_code == 404

    # The moderators see it all on their page, and their decision closes the case for everyone.
    be(client, "Ana_99")
    [row] = client.get(f"/api/clubs/{slug}/reports").json()["reports"]
    assert row["public_id"] == pid and row["priority"] == "urgent" and row["status"] == "triaged"
    assert row["triage"]["label"] == "hate" and row["tickets"] == [
        {"system": "jira", "key": "SNZ-12", "url": "https://jira.example.test/SNZ-12"}
    ]
    assert [h["text"] for h in row["history"]] == [
        "Reported",
        "Triage: hate (93%); priority urgent; status triaged",
        "Linked jira SNZ-12",
    ]
    assert row["can_act"] is True
    client.post(f"/api/clubs/{slug}/reports/{row['id']}", json={"action": "ban"})
    r = client.post(url, json={"source": "jira", "status": "open"}, headers=AUTH)
    assert r.json()["error"]["code"] == "handled"
    one = client.get(url, headers=AUTH).json()
    assert one["report"]["status"] == "actioned" and one["timeline"][-1]["actor"] == "user:Ana_99"


def test_without_a_token_the_integration_api_does_not_exist(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        assert c.get("/api/integrations/reports", headers=AUTH).status_code == 404
        assert c.get("/api/integrations/health", headers=AUTH).status_code == 404


def test_pseudonyms_are_stable_and_opaque():
    a = events.pseudonym("k" * 40, "user", 12)
    assert a == events.pseudonym("k" * 40, "user", 12) and a != events.pseudonym("k" * 40, "user", 13)
    assert a != events.pseudonym("j" * 40, "user", 12) and "12" not in a[4:6]
    assert events.pseudonym("k" * 40, "user", None) is None
