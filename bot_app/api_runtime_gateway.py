"""Typed FSM and lease operations mixed into the bot HTTP gateway."""

from api_contracts.bot import BotFsmStateResponse, BotRuntimeLeaseResponse


class BotApiRuntimeMixin:
    async def get_fsm_state(self, *, storage_key: str) -> BotFsmStateResponse:
        payload = await self._post("fsm/get", json={"storage_key": storage_key})
        return self._validate_contract(BotFsmStateResponse, payload, "FSM state")

    async def update_fsm_state(self, **values) -> BotFsmStateResponse:
        payload = await self._post("fsm/update", json=values)
        return self._validate_contract(BotFsmStateResponse, payload, "FSM update")

    async def acquire_runtime_lease(
        self, *, name: str, owner_id: str, ttl_seconds: int
    ) -> BotRuntimeLeaseResponse:
        return await self._lease("acquire", name, owner_id, ttl_seconds)

    async def renew_runtime_lease(
        self, *, name: str, owner_id: str, ttl_seconds: int
    ) -> BotRuntimeLeaseResponse:
        return await self._lease("renew", name, owner_id, ttl_seconds)

    async def release_runtime_lease(
        self, *, name: str, owner_id: str, ttl_seconds: int
    ) -> BotRuntimeLeaseResponse:
        return await self._lease("release", name, owner_id, ttl_seconds)

    async def _lease(
        self, action: str, name: str, owner_id: str, ttl_seconds: int
    ) -> BotRuntimeLeaseResponse:
        payload = await self._post(
            f"runtime-leases/{action}",
            json={"name": name, "owner_id": owner_id, "ttl_seconds": ttl_seconds},
        )
        return self._validate_contract(BotRuntimeLeaseResponse, payload, "runtime lease")
