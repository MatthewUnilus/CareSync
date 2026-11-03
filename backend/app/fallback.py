"""The runtime fallback for complaints no Symptom Group matched.

This is layer (3) of the Prioritization Engine (``spec.md``, "Prioritization
Engine composition"). It is only reached for a complaint whose recognition
result is empty; a complaint that matches a Symptom Group never comes here.

The layer is deliberately a seam rather than a vendor call baked into the
engine:

* :class:`FallbackProvider` is the tiny protocol a provider implements.
  :class:`HttpFallbackProvider` is the runtime implementation; the test suite
  injects a fake and never needs an API key, a network or a paid service.
* :class:`FallbackResolver` owns the policy around a provider: the cache lookup
  keyed by a hash of the complaint text, the timeout, and the degraded path.
* :class:`FallbackCache` is the storage seam. The application backs it with the
  ``fallback_cache`` database table (``app.fallback_cache``), so a hit survives
  a process restart; :class:`MemoryFallbackCache` exists for tests and for a
  caller that has no session.

Why the cache stores the provider's raw level
---------------------------------------------
The safety layer is a function of the *whole* presentation: a cached answer for
"metallic taste" must still be raised to High for a hypoxaemic patient who
happens to use the same words. The cache therefore stores only the provider's
complaint-only answer and the safety layer is applied on every resolve, cache
hit included.

Timeout policy
--------------
A provider call may fail or exceed its timeout. Neither is an error the
patient sees: the resolver falls back to :data:`DEFAULT_TIMEOUT_LEVEL` (Medium)
and runs the safety layer over it, so a red flag can still raise the result to
High. The outcome is marked ``unclassified`` so the card can ask for review.
Medium is the documented default because it neither systematically under- nor
over-triages on its own, and High would leave the safety layer nothing to
raise.

A timeout or failure is not cached: the degraded answer is deterministic
already (the safety layer is pure), and caching it would keep a transient
outage in the record after the provider recovered.
"""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.config import Settings
    from app.prioritisation import PrioritisationInputs, UrgencyLevel

#: A provider that does not answer in time falls back to this level. It is
#: deliberately not High: the safety layer must still be able to raise it.
DEFAULT_TIMEOUT_LEVEL = "Medium"
DEFAULT_TIMEOUT_SECONDS = 2.0

_VALID_LEVELS = ("High", "Medium", "Low")


class FallbackUnavailable(RuntimeError):
    """The fallback provider is not configured, failed, or returned nonsense."""


class FallbackTimeout(FallbackUnavailable):
    """The fallback provider did not answer inside the timeout."""


class FallbackProvider(Protocol):
    """One external service that maps complaint text to an Urgency Level."""

    @property
    def name(self) -> str:
        """A stable name recorded with a cached answer."""

    def classify(self, complaint: str) -> "UrgencyLevel":
        """Return the provider's own Urgency Level for the complaint."""


class FallbackCache(Protocol):
    """Storage for provider answers, keyed by a hash of the complaint text."""

    def get(self, complaint_hash: str) -> "FallbackCacheHit | None":
        """Return a stored answer, or ``None`` on a miss."""

    def put(
        self,
        *,
        complaint_hash: str,
        complaint: str,
        urgency_level: "UrgencyLevel",
        provider: str,
    ) -> None:
        """Store an answer; a later resolve must return it unchanged."""


@dataclass(frozen=True)
class FallbackCacheHit:
    urgency_level: "UrgencyLevel"
    provider: str


@dataclass(frozen=True)
class FallbackOutcome:
    """What the fallback layer contributed to the Machine Recommendation."""

    level: "UrgencyLevel"
    unclassified: bool = False


class MemoryFallbackCache:
    """An in-process cache, used by tests and by callers without a session."""

    def __init__(self) -> None:
        self._entries: dict[str, FallbackCacheHit] = {}
        self.hits = 0

    def get(self, complaint_hash: str) -> FallbackCacheHit | None:
        hit = self._entries.get(complaint_hash)
        if hit is not None:
            self.hits += 1
        return hit

    def put(
        self,
        *,
        complaint_hash: str,
        complaint: str,
        urgency_level: "UrgencyLevel",
        provider: str,
    ) -> None:
        self._entries[complaint_hash] = FallbackCacheHit(
            urgency_level=urgency_level,
            provider=provider,
        )


class UnavailableFallbackProvider:
    """The provider used when no runtime service is configured.

    It raises on every call, so an unconfigured deployment takes exactly the
    same degraded path as an outage. Nothing about the build or the test suite
    depends on a key or a network.
    """

    def __init__(self, reason: str = "no fallback provider is configured"):
        self.reason = reason

    @property
    def name(self) -> str:
        return "unavailable"

    def classify(self, complaint: str) -> "UrgencyLevel":
        raise FallbackUnavailable(self.reason)


class HttpFallbackProvider:
    """A provider speaking a minimal JSON contract over HTTP.

    Request: ``POST <url>`` with ``{"complaint": "<text>"}`` and, when an API
    key is configured, ``Authorization: Bearer <key>``.

    Response: ``{"urgency_level": "High" | "Medium" | "Low"}`` (or a plain body
    containing one of those words). The contract is intentionally vendor-neutral
    so a deployment can point it at any service; the seam, not the vendor, is
    the design decision.
    """

    def __init__(
        self,
        url: str,
        *,
        api_key: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "http"

    def classify(self, complaint: str) -> "UrgencyLevel":
        from app.prioritisation import UrgencyLevel

        body = json.dumps({"complaint": complaint}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.url, data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise FallbackUnavailable(str(error)) from error

        return _parse_provider_body(raw, UrgencyLevel)


def _parse_provider_body(raw: str, urgency_level: type) -> "UrgencyLevel":
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw.strip()

    value: object
    if isinstance(payload, dict):
        value = payload.get("urgency_level", payload.get("level"))
    else:
        value = payload
    if not isinstance(value, str):
        raise FallbackUnavailable("fallback provider returned no Urgency Level")

    for candidate in _VALID_LEVELS:
        if value.strip().casefold() == candidate.casefold():
            return urgency_level(candidate)
    raise FallbackUnavailable(
        f"fallback provider returned an unknown Urgency Level: {value!r}"
    )


def complaint_hash(complaint: str) -> str:
    """The cache key: a stable SHA-256 of the complaint text exactly as stored."""
    return hashlib.sha256(complaint.encode("utf-8")).hexdigest()


def _call_with_timeout(function, timeout_seconds: float):
    """Run ``function`` and raise :class:`FallbackTimeout` after the deadline.

    A daemon thread is used rather than a signal so the behaviour is the same on
    every platform and inside a request thread. A timed-out worker is abandoned;
    it holds no database session and cannot write to the cache.
    """
    outcome: dict[str, object] = {}
    finished = threading.Event()

    def run() -> None:
        try:
            outcome["value"] = function()
        except BaseException as error:  # noqa: BLE001 - relayed to the caller
            outcome["error"] = error
        finally:
            finished.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    if not finished.wait(timeout_seconds):
        raise FallbackTimeout(
            f"fallback provider did not answer within {timeout_seconds:g}s"
        )
    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    return outcome.get("value")


class FallbackResolver:
    """The fallback policy: cache, timeout, and rules-on-degrade."""

    def __init__(
        self,
        provider: FallbackProvider,
        *,
        cache: FallbackCache | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        default_level: str = DEFAULT_TIMEOUT_LEVEL,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("fallback timeout must be positive")
        self.provider = provider
        self.cache = cache
        self.timeout_seconds = timeout_seconds
        self.default_level = default_level

    def resolve(self, inputs: "PrioritisationInputs") -> FallbackOutcome:
        """Resolve one unmatched complaint, never raising for provider failure."""
        from app.prioritisation import UrgencyLevel
        from app.red_flags import apply_safety_layer

        key = complaint_hash(inputs.presenting_complaint)

        if self.cache is not None:
            try:
                hit = self.cache.get(key)
            except Exception:  # noqa: BLE001 - cache unavailability is not fatal
                hit = None
            if hit is not None:
                return FallbackOutcome(
                    level=apply_safety_layer(inputs, hit.urgency_level),
                )

        try:
            raw = _call_with_timeout(
                lambda: self.provider.classify(inputs.presenting_complaint),
                self.timeout_seconds,
            )
            level = _coerce_level(raw, UrgencyLevel)
        except Exception:  # noqa: BLE001 - an outage degrades, never crashes
            default = _coerce_level(self.default_level, UrgencyLevel)
            return FallbackOutcome(
                level=apply_safety_layer(inputs, default),
                unclassified=True,
            )

        if self.cache is not None:
            try:
                self.cache.put(
                    complaint_hash=key,
                    complaint=inputs.presenting_complaint,
                    urgency_level=level,
                    provider=getattr(
                        self.provider, "name", type(self.provider).__name__
                    ),
                )
            except Exception:  # noqa: BLE001 - a missed cache write is harmless
                pass

        return FallbackOutcome(level=apply_safety_layer(inputs, level))


def _coerce_level(value: object, urgency_level: type) -> "UrgencyLevel":
    if isinstance(value, urgency_level):
        return value
    if isinstance(value, str):
        for candidate in _VALID_LEVELS:
            if value.strip().casefold() == candidate.casefold():
                return urgency_level(candidate)
    raise FallbackUnavailable(
        f"fallback provider returned an unknown Urgency Level: {value!r}"
    )


def build_fallback_provider(settings: "Settings") -> FallbackProvider:
    """Build the runtime provider from configuration.

    No URL means no provider: the engine then takes the degraded path rather
    than failing. An API key is optional so a local service can be used without
    one, and is sent as a bearer token when present.
    """
    url = getattr(settings, "fallback_provider_url", None)
    if not url:
        return UnavailableFallbackProvider()
    return HttpFallbackProvider(
        url,
        api_key=getattr(settings, "fallback_provider_api_key", None),
        timeout_seconds=getattr(
            settings, "fallback_timeout_seconds", DEFAULT_TIMEOUT_SECONDS
        ),
    )


__all__ = [
    "DEFAULT_TIMEOUT_LEVEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "FallbackCache",
    "FallbackCacheHit",
    "FallbackOutcome",
    "FallbackProvider",
    "FallbackResolver",
    "FallbackTimeout",
    "FallbackUnavailable",
    "HttpFallbackProvider",
    "MemoryFallbackCache",
    "UnavailableFallbackProvider",
    "build_fallback_provider",
    "complaint_hash",
]
