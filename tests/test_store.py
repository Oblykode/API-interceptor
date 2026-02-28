from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.models import PacketMessage, ProxyConfig, RequestDecisionIn
from app.state.repository import SQLiteRepository
from app.state.store import InterceptionStore


@pytest.mark.asyncio
async def test_queue_enforces_head_only(tmp_path: Path) -> None:
    repo = SQLiteRepository(str(tmp_path / "test.db"))
    await repo.init()
    store = InterceptionStore(
        repo,
        ProxyConfig(max_flows_memory=100, flow_retention_minutes=30),
    )
    await store.start()

    await store.upsert_request("flow-1", PacketMessage(method="GET", url="http://example.com/1"))
    await store.upsert_request("flow-2", PacketMessage(method="GET", url="http://example.com/2"))

    with pytest.raises(ValueError):
        await store.set_request_decision("flow-2", RequestDecisionIn(action="forward"))

    await store.set_request_decision("flow-1", RequestDecisionIn(action="forward"))
    decision = await store.take_request_decision("flow-1")
    assert decision.decision is not None

    queue = await store.queue_state()
    assert queue.active == "flow-2"
    await repo.close()

