import json
from pathlib import Path

import httpx

from agent.clinic.adapter import ClinicAdapter, ClinicPolicy
from agent.clinic.clinic_a import ClinicAAdapter
from agent.clinic.clinic_b import ClinicBAdapter

POLICY_DIR = Path(__file__).parent / "policies"
ADAPTERS: dict[str, type[ClinicAdapter]] = {"clinic_a": ClinicAAdapter, "clinic_b": ClinicBAdapter}


def load_policy(clinic_id: str) -> ClinicPolicy:
    return ClinicPolicy(**json.loads((POLICY_DIR / f"{clinic_id}.json").read_text(encoding="utf-8")))


class Registry:
    def __init__(self, adapters: dict[str, ClinicAdapter], enabled: tuple[str, ...]):
        self.adapters = adapters
        self.enabled_ids = [clinic_id for clinic_id in enabled if clinic_id in adapters]

    def enabled(self) -> list[ClinicAdapter]:
        return [self.adapters[clinic_id] for clinic_id in self.enabled_ids]

    def get(self, clinic_id: str) -> ClinicAdapter:
        return self.adapters[clinic_id]

    def is_enabled(self, clinic_id: str) -> bool:
        return clinic_id in self.enabled_ids

    def default(self) -> ClinicAdapter:
        return self.enabled()[0]

    def set_enabled(self, clinic_id: str, enabled: bool) -> None:
        if enabled and clinic_id in self.adapters and clinic_id not in self.enabled_ids:
            self.enabled_ids.append(clinic_id)
        if not enabled and clinic_id in self.enabled_ids and len(self.enabled_ids) > 1:
            self.enabled_ids.remove(clinic_id)


def build_registry(client: httpx.AsyncClient, api_key: str, timeout_s: float, enabled: tuple[str, ...]) -> Registry:
    adapters = {
        clinic_id: adapter(load_policy(clinic_id), client, api_key, timeout_s) for clinic_id, adapter in ADAPTERS.items()
    }
    return Registry(adapters, enabled)
