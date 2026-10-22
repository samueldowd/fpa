"""Local funnel allowance, independent of every reported appliance alert."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import Preparation, integer, mapping, number

FUNNEL_CAPACITY = 4


@dataclass
class FunnelCounter:
    """Persist the allowance and a small completion cursor, never bottle history."""

    remaining: int = FUNNEL_CAPACITY
    initialized: bool = False
    completed_at: int | float | None = None
    record_id: str | int | None = None
    removed: bool | None = None

    @classmethod
    def from_storage(cls, raw: Any) -> FunnelCounter:
        raw = mapping(raw)
        remaining = integer(raw.get("remaining"))
        record_id = raw.get("record_id")
        return cls(
            remaining=FUNNEL_CAPACITY
            if remaining is None
            else max(0, min(FUNNEL_CAPACITY, remaining)),
            initialized=raw.get("initialized") is True,
            completed_at=number(raw.get("completed_at")),
            record_id=record_id
            if isinstance(record_id, (str, int)) and not isinstance(record_id, bool)
            else None,
            removed=raw.get("removed")
            if isinstance(raw.get("removed"), bool)
            else None,
        )

    def persistent(self) -> dict[str, Any]:
        return asdict(self)

    def observe(
        self,
        preparation: Preparation | None,
        removed: bool | None,
        *,
        initialize: bool = False,
    ) -> None:
        """Count distinct completions once; first setup establishes a baseline."""
        if self.initialized and preparation is not None:
            timestamp = preparation.completed_at.timestamp()
            if (
                self.completed_at is None
                or timestamp > self.completed_at
                or (
                    timestamp == self.completed_at
                    and self.record_id is not None
                    and preparation.record_id is not None
                    and self.record_id != preparation.record_id
                )
            ):
                self.remaining = max(0, self.remaining - 1)
        if (self.initialized or initialize) and preparation is not None:
            timestamp = preparation.completed_at.timestamp()
            if self.completed_at is None or timestamp >= self.completed_at:
                if preparation.record_id is not None or timestamp != self.completed_at:
                    self.record_id = preparation.record_id
                self.completed_at = timestamp
        if initialize:
            self.initialized = True
        if removed is True and self.removed is not True:
            # Removal wins if a completion and removal arrive together.
            self.reset()
        if removed is not None:
            self.removed = removed

    def reset(self) -> None:
        """Reset only the local allowance, retaining the deduplication cursor."""
        self.remaining = FUNNEL_CAPACITY
