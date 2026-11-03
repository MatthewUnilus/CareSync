"""Seam B: the cached fallback for complaints no Symptom Group matched.

The fallback is the third layer of the engine. It is only reached when the
complaint recognises no Symptom Group, it is cached by the complaint text, and
it degrades to the safety layer alone -- never to an error -- when the external
provider is unavailable or slow. These tests inject fake providers: the suite
needs no API key, network or paid service.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import threading

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.fallback import FallbackResolver, MemoryFallbackCache
from app.main import create_app
from app.prioritisation import PrioritisationInputs, UrgencyLevel, assess

# A quiet young adult whose complaint recognises no Symptom Group. The
# vocabulary is literal, so "metallic taste" cannot accidentally match.
BASE_INPUTS = PrioritisationInputs(
    presenting_complaint="Metallic taste in mouth",
    age=24,
    pain_level=2,
    illness_duration_hours=24.0,
    temperature_c=36.6,
    heart_rate_bpm=70,
    systolic_bp=116,
    diastolic_bp=72,
    oxygen_saturation_percent=99,
)

UNMATCHED_COMPLAINT = "Metallic taste in mouth"

ALL_LEVELS = {UrgencyLevel.high, UrgencyLevel.medium, UrgencyLevel.low}


@dataclass
class FakeProvider:
    """A provider that answers deterministically and records every call."""

    level: UrgencyLevel = UrgencyLevel.low
    calls: list[str] = field(default_factory=list)

    def classify(self, complaint: str) -> UrgencyLevel:
        self.calls.append(complaint)
        return self.level


@dataclass
class FailingProvider:
    calls: list[str] = field(default_factory=list)

    def classify(self, complaint: str) -> UrgencyLevel:
        self.calls.append(complaint)
        raise RuntimeError("fallback service is down")


@dataclass
class SlowProvider:
    delay_seconds: float = 0.4
    calls: list[str] = field(default_factory=list)

    def classify(self, complaint: str) -> UrgencyLevel:
        self.calls.append(complaint)
        threading.Event().wait(self.delay_seconds)
        return UrgencyLevel.high


def resolver(
    provider: object,
    *,
    cache: object | None = None,
    timeout_seconds: float = 2.0,
) -> FallbackResolver:
    return FallbackResolver(
        provider,  # type: ignore[arg-type]
        cache=cache,  # type: ignore[arg-type]
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# Seam B: the engine with an injected provider and cache
# ---------------------------------------------------------------------------


def test_an_unrecognised_complaint_receives_the_provider_recommendation() -> None:
    outcome = assess(BASE_INPUTS, fallback=resolver(FakeProvider(UrgencyLevel.medium)))

    assert outcome.level is UrgencyLevel.medium
    assert outcome.fallback_used is True
    assert outcome.unclassified is False


def test_the_safety_layer_can_raise_the_fallback_result() -> None:
    case = replace(BASE_INPUTS, oxygen_saturation_percent=88)

    outcome = assess(case, fallback=resolver(FakeProvider(UrgencyLevel.low)))

    assert outcome.level is UrgencyLevel.high
    assert outcome.unclassified is False


def test_the_same_complaint_twice_returns_identical_results_from_cache() -> None:
    provider = FakeProvider(UrgencyLevel.medium)
    cache = MemoryFallbackCache()
    fallback = resolver(provider, cache=cache)

    first = assess(BASE_INPUTS, fallback=fallback)
    second = assess(BASE_INPUTS, fallback=fallback)

    assert first == second
    assert provider.calls == [UNMATCHED_COMPLAINT]
    assert cache.hits == 1


def test_a_provider_failure_is_unclassified_and_still_a_valid_level() -> None:
    provider = FailingProvider()

    outcome = assess(BASE_INPUTS, fallback=resolver(provider))

    assert provider.calls == [UNMATCHED_COMPLAINT]
    assert outcome.unclassified is True
    assert outcome.level in ALL_LEVELS
    assert outcome.level is UrgencyLevel.medium


def test_a_provider_timeout_is_unclassified_and_still_a_valid_level() -> None:
    provider = SlowProvider()

    outcome = assess(
        BASE_INPUTS,
        fallback=resolver(provider, timeout_seconds=0.05),
    )

    assert provider.calls == [UNMATCHED_COMPLAINT]
    assert outcome.unclassified is True
    assert outcome.level in ALL_LEVELS
    assert outcome.level is UrgencyLevel.medium


def test_the_timeout_default_can_be_raised_by_a_red_flag() -> None:
    case = replace(BASE_INPUTS, oxygen_saturation_percent=88)

    outcome = assess(
        case,
        fallback=resolver(SlowProvider(), timeout_seconds=0.05),
    )

    assert outcome.unclassified is True
    assert outcome.level is UrgencyLevel.high


def test_a_matched_complaint_never_takes_the_fallback_path() -> None:
    provider = FakeProvider(UrgencyLevel.low)
    case = replace(
        BASE_INPUTS,
        presenting_complaint="Crushing chest pain",
        recognised_symptom_groups=("chest pain",),
    )

    outcome = assess(case, fallback=resolver(provider))

    assert outcome.fallback_used is False
    assert outcome.unclassified is False
    assert provider.calls == []
    # The safety layer, not the provider, makes this High.
    assert outcome.level is UrgencyLevel.high


def test_the_engine_without_a_fallback_is_the_classifier_and_safety_layer() -> None:
    outcome = assess(BASE_INPUTS)

    assert outcome.level is UrgencyLevel.low
    assert outcome.fallback_used is False
    assert outcome.unclassified is False


def test_a_complaint_with_a_different_hash_is_a_separate_cache_entry() -> None:
    provider = FakeProvider(UrgencyLevel.medium)
    cache = MemoryFallbackCache()
    fallback = resolver(provider, cache=cache)

    assess(BASE_INPUTS, fallback=fallback)
    assess(
        replace(BASE_INPUTS, presenting_complaint="A different odd complaint"),
        fallback=fallback,
    )

    assert len(provider.calls) == 2
    assert cache.hits == 0


# ---------------------------------------------------------------------------
# Seam A: the API stores the fallback result and persists the cache
# ---------------------------------------------------------------------------

LOW_INTAKE = {
    "presenting_complaint": UNMATCHED_COMPLAINT,
    "pain_level": 2,
    "illness_duration_hours": 24,
    "temperature_c": 36.6,
    "heart_rate_bpm": 70,
    "blood_pressure": {"systolic": 116, "diastolic": 72},
    "oxygen_saturation_percent": 99,
    "notes": None,
}


@contextmanager
def api_client(db_path, provider: object | None = None, timeout: float = 2.0):
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_ttl_seconds=3600,
        seed_demo_users=True,
        fallback_timeout_seconds=timeout,
    )
    with TestClient(
        create_app(settings, fallback_provider=provider)
    ) as client:
        response = client.post(
            "/api/auth/login",
            json={
                "email": "clinical@example.com",
                "password": "clinical-password",
            },
        )
        assert response.status_code == 200
        yield client


def register_patient(client: TestClient, name: str) -> int:
    response = client.post(
        "/api/clinical/patients",
        json={
            "full_name": name,
            "age": 24,
            "sex": "female",
            "contact_phone": "07700 900123",
            "contact_email": None,
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def open_encounter(
    client: TestClient, patient_id: int, complaint: str = UNMATCHED_COMPLAINT
) -> dict:
    response = client.post(
        "/api/clinical/encounters",
        json={
            "patient_id": patient_id,
            "intake": {**LOW_INTAKE, "presenting_complaint": complaint},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def queue_entry(client: TestClient, encounter_id: int) -> dict:
    entries = client.get("/api/clinical/queue").json()["entries"]
    return next(
        entry for entry in entries if entry["encounter_id"] == encounter_id
    )


def test_an_unmatched_complaint_is_stored_with_the_fallback_recommendation(
    db_path,
) -> None:
    provider = FakeProvider(UrgencyLevel.low)
    with api_client(db_path, provider) as client:
        encounter = open_encounter(client, register_patient(client, "Ada Lovelace"))

        assessment = encounter["assessment"]
        assert assessment["recognised_symptom_groups"] == []
        assert assessment["machine_recommendation"] == "Low"
        assert assessment["unclassified"] is False

        entry = queue_entry(client, encounter["id"])
        assert entry["unclassified_flag"] is False
        assert entry["override_flag"] is False


def test_the_same_complaint_is_served_from_the_database_cache(db_path) -> None:
    provider = FakeProvider(UrgencyLevel.low)
    with api_client(db_path, provider) as client:
        first = open_encounter(client, register_patient(client, "Ada Lovelace"))
        second = open_encounter(client, register_patient(client, "Grace Hopper"))

        assert (
            first["assessment"]["machine_recommendation"]
            == second["assessment"]["machine_recommendation"]
        )
        assert provider.calls == [UNMATCHED_COMPLAINT]


def test_the_cache_survives_a_new_application_instance(db_path) -> None:
    with api_client(db_path, FakeProvider(UrgencyLevel.low)) as client:
        first = open_encounter(client, register_patient(client, "Ada Lovelace"))

    later_provider = FakeProvider(UrgencyLevel.high)
    with api_client(db_path, later_provider) as client:
        second = open_encounter(client, register_patient(client, "Grace Hopper"))

    assert first["assessment"]["machine_recommendation"] == "Low"
    assert second["assessment"]["machine_recommendation"] == "Low"
    assert later_provider.calls == []


def test_an_unconfigured_provider_degrades_to_an_unclassified_recommendation(
    db_path,
) -> None:
    with api_client(db_path) as client:
        encounter = open_encounter(client, register_patient(client, "Ada Lovelace"))

        assessment = encounter["assessment"]
        assert assessment["machine_recommendation"] == "Medium"
        assert assessment["unclassified"] is True

        entry = queue_entry(client, encounter["id"])
        assert entry["unclassified_flag"] is True
        assert entry["override_flag"] is False


def test_unclassified_and_override_are_separate_flags(db_path) -> None:
    with api_client(db_path) as client:
        encounter = open_encounter(client, register_patient(client, "Ada Lovelace"))
        assessment = encounter["assessment"]

        response = client.post(
            f"/api/clinical/encounters/{encounter['id']}/override",
            json={
                "assessment_id": assessment["id"],
                "final_decision": "High",
                "reason": "clinical gestalt",
                "free_text": None,
            },
        )
        assert response.status_code == 200, response.text

        entry = queue_entry(client, encounter["id"])
        assert entry["unclassified_flag"] is True
        assert entry["override_flag"] is True


@pytest.mark.parametrize(
    "framework_detail",
    ["a provider that raises", "a provider that times out"],
)
def test_provider_failure_and_timeout_both_yield_a_valid_level(
    db_path, framework_detail: str
) -> None:
    provider: object
    timeout = 2.0
    if framework_detail == "a provider that raises":
        provider = FailingProvider()
    else:
        provider = SlowProvider()
        timeout = 0.05

    with api_client(db_path, provider, timeout=timeout) as client:
        encounter = open_encounter(client, register_patient(client, "Ada Lovelace"))

        assessment = encounter["assessment"]
        assert assessment["machine_recommendation"] in {"High", "Medium", "Low"}
        assert assessment["unclassified"] is True
        assert assessment["final_decision"] == assessment["machine_recommendation"]


def test_a_matched_complaint_bypasses_an_unavailable_fallback(db_path) -> None:
    provider = FakeProvider(UrgencyLevel.low)
    with api_client(db_path, provider) as client:
        encounter = open_encounter(
            client, register_patient(client, "Ada Lovelace"), "Crushing chest pain"
        )

        assessment = encounter["assessment"]
        assert assessment["recognised_symptom_groups"] == ["chest pain"]
        assert assessment["machine_recommendation"] == "High"
        assert assessment["unclassified"] is False
        assert provider.calls == []

        entry = queue_entry(client, encounter["id"])
        assert entry["unclassified_flag"] is False
