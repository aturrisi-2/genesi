import csv
import io

import pytest

from core.fallback_engine import FallbackEngine


def _engine_with_events(events):
    engine = object.__new__(FallbackEngine)
    engine.events = events
    return engine


def test_fallback_summary_tolerates_missing_group_key():
    engine = _engine_with_events(
        [
            {
                "id": "old-1",
                "timestamp": "2026-06-28T10:00:00",
                "user_id": "u1",
                "user_message": "messaggio legacy",
                "response_given": "fallback",
                "fallback_type": "legacy",
                "reason": "old event",
                "possible_solution": "check",
            },
            {
                "id": "new-1",
                "timestamp": "2026-06-28T10:01:00",
                "user_id": "u1",
                "user_message": "messaggio legacy",
                "response_given": "fallback",
                "fallback_type": "legacy",
                "reason": "new event",
                "group_key": "known-key",
                "possible_solution": "check",
            },
        ]
    )

    summary = engine.get_summary()

    assert len(summary) == 2
    assert {item["count"] for item in summary} == {1}
    assert all(item["examples"] for item in summary)


@pytest.mark.asyncio
async def test_fallback_csv_tolerates_missing_and_extra_fields(monkeypatch):
    from api import admin_fallback

    class FakeEngine:
        def get_all_raw(self):
            return [
                {
                    "id": "old-1",
                    "timestamp": "2026-06-28T10:00:00",
                    "user_id": "u1",
                    "user_message": "legacy",
                    "response_given": "fallback",
                    "fallback_type": "legacy",
                    "reason": "old event",
                    "status": "pending",
                    "unexpected": "ignored",
                },
                {
                    "id": "new-1",
                    "timestamp": "2026-06-28T10:01:00",
                    "user_id": "u2",
                    "user_message": "new",
                    "response_given": "fallback",
                    "fallback_type": "new",
                    "reason": "new event",
                    "group_key": "known-key",
                    "possible_solution": "check",
                    "status": "pending",
                },
            ]

    monkeypatch.setattr(admin_fallback, "fallback_engine", FakeEngine())

    response = await admin_fallback.download_fallbacks_csv(user=object())
    body = b""
    async for chunk in response.body_iterator:
        body += chunk

    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))

    assert rows[0]["group_key"] == ""
    assert rows[1]["group_key"] == "known-key"
    assert "unexpected" not in rows[0]
