from __future__ import annotations

import threading

from mini_flood.mdns_advertiser import MdnsAdvertiser


def test_mdns_run_retries_then_stops(monkeypatch):
    advertiser = MdnsAdvertiser("mini-flood-backend", 8000, enabled=True)
    stop_event = threading.Event()
    attempts = []
    stopped = []

    def fake_start() -> bool:
        attempts.append(len(attempts) + 1)
        if len(attempts) == 2:
            stop_event.set()
            return True
        return False

    monkeypatch.setattr(advertiser, "start", fake_start)
    monkeypatch.setattr(advertiser, "stop", lambda: stopped.append(True))

    advertiser.run(stop_event, retry_seconds=0.001)

    assert attempts == [1, 2]
    assert stopped == [True]


def test_mdns_run_is_noop_when_disabled(monkeypatch):
    advertiser = MdnsAdvertiser("mini-flood-backend", 8000, enabled=False)
    started = []
    stopped = []
    monkeypatch.setattr(advertiser, "start", lambda: started.append(True))
    monkeypatch.setattr(advertiser, "stop", lambda: stopped.append(True))

    advertiser.run(threading.Event(), retry_seconds=0.001)

    assert started == []
    assert stopped == []
