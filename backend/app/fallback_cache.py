"""Database-backed storage for the fallback provider's cached answers.

The engine itself stays pure (Seam B): this adapter is handed to it only from
the application path that already holds a database session. Because the row is
committed with the Assessment, a cache hit survives a process restart and is
shared by every worker that reads the same database.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.fallback import FallbackCacheHit
from app.models import FallbackCacheEntry
from app.prioritisation import UrgencyLevel


class DatabaseFallbackCache:
    """A :class:`app.fallback.FallbackCache` backed by ``fallback_cache``."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, complaint_hash: str) -> FallbackCacheHit | None:
        entry = self._session.get(FallbackCacheEntry, complaint_hash)
        if entry is None:
            return None
        return FallbackCacheHit(
            urgency_level=UrgencyLevel(entry.machine_recommendation),
            provider=entry.provider,
        )

    def put(
        self,
        *,
        complaint_hash: str,
        complaint: str,
        urgency_level: UrgencyLevel,
        provider: str,
    ) -> None:
        # ``merge`` makes a concurrent duplicate a no-op rather than a primary
        # key violation. The value is the same by construction: the key is the
        # hash of the exact complaint text.
        self._session.merge(
            FallbackCacheEntry(
                complaint_hash=complaint_hash,
                presenting_complaint=complaint,
                machine_recommendation=urgency_level.value,
                provider=provider,
            )
        )
        self._session.flush()


__all__ = ["DatabaseFallbackCache"]
