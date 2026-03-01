"""Configuration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_store
from app.domain.models import ApiEnvelope, ProxyConfig, TargetIpsUpdateIn
from app.state.store import InterceptionStore

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=ApiEnvelope[ProxyConfig])
async def get_config(store: InterceptionStore = Depends(get_store)) -> ApiEnvelope[ProxyConfig]:
    cfg = await store.get_config()
    return ApiEnvelope(data=cfg)


@router.put("", response_model=ApiEnvelope[ProxyConfig])
async def update_config(cfg: ProxyConfig, store: InterceptionStore = Depends(get_store)) -> ApiEnvelope[ProxyConfig]:
    updated = await store.update_config(cfg)
    return ApiEnvelope(data=updated)


@router.post("/target_ips", response_model=ApiEnvelope[ProxyConfig])
async def update_target_ips(
    payload: TargetIpsUpdateIn,
    store: InterceptionStore = Depends(get_store),
) -> ApiEnvelope[ProxyConfig]:
    cfg = await store.get_config()
    cfg.target_ips = payload.target_ips
    cfg.intercept_all = len(payload.target_ips) == 0
    updated = await store.update_config(cfg)
    return ApiEnvelope(data=updated)


@router.get("/info", response_model=ApiEnvelope[dict])
async def config_info(store: InterceptionStore = Depends(get_store)) -> ApiEnvelope[dict]:
    cfg = await store.get_config()
    return ApiEnvelope(
        data={
            "target_ips": cfg.target_ips,
            "intercept_all": cfg.intercept_all,
            "filter_mode": "All Traffic" if cfg.intercept_all else f"IP Filter ({len(cfg.target_ips)} targets)",
        }
    )
