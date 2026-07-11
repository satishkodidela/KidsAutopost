"""Hard spend caps and a cost ledger (data/costs.json).

Every clip generation calls charge() BEFORE the API call — attempts that get
filtered or discarded still cost money. A run that would blow the per-run or
monthly cap aborts cleanly; staged partials stay on disk for a resumed run.
"""

import datetime as dt
import json
from pathlib import Path

import config

# $ per generated second by backend. Veo 3.1 fast list price; Kie is
# credits-based so KIE_USD_PER_SECOND should reflect the operator's actual
# credit pack pricing.
RATES = {
    "veo": config.env_float("VEO_USD_PER_SECOND", 0.15),
    "seedance": config.env_float("KIE_USD_PER_SECOND", 0.02),
}


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, path: Path | None = None, now: dt.date | None = None):
        self.path = path or config.COSTS_PATH
        self.now = now or dt.date.today()
        self.max_run = config.env_float("MAX_USD_PER_RUN", 12.0)
        self.max_month = config.env_float("MAX_USD_PER_MONTH", 200.0)
        self.run_spent = 0.0
        self._ledger = (
            json.loads(self.path.read_text()) if self.path.exists() else {"months": {}, "entries": []}
        )

    @property
    def month_key(self) -> str:
        return self.now.strftime("%Y-%m")

    def month_spent(self) -> float:
        return float(self._ledger["months"].get(self.month_key, 0.0))

    def precheck(self, n_clips: int, clip_seconds: int, backend: str) -> float:
        """Estimate base cost + 30% regen reserve; raise if it can't fit."""
        estimate = n_clips * clip_seconds * RATES[backend] * 1.3
        if estimate > self.max_run:
            raise BudgetExceeded(
                f"Estimated ${estimate:.2f} exceeds MAX_USD_PER_RUN ${self.max_run:.2f}"
            )
        if self.month_spent() + estimate > self.max_month:
            raise BudgetExceeded(
                f"Estimated ${estimate:.2f} + ${self.month_spent():.2f} spent this month "
                f"exceeds MAX_USD_PER_MONTH ${self.max_month:.2f}"
            )
        return estimate

    def charge(self, seconds: float, backend: str, note: str = "") -> float:
        cost = seconds * RATES[backend]
        if self.run_spent + cost > self.max_run:
            raise BudgetExceeded(
                f"Charge ${cost:.2f} would exceed MAX_USD_PER_RUN "
                f"(${self.run_spent:.2f} spent this run)"
            )
        if self.month_spent() + cost > self.max_month:
            raise BudgetExceeded(
                f"Charge ${cost:.2f} would exceed MAX_USD_PER_MONTH "
                f"(${self.month_spent():.2f} spent this month)"
            )
        self.run_spent += cost
        self._ledger["months"][self.month_key] = round(self.month_spent() + cost, 4)
        self._ledger["entries"].append(
            {"date": self.now.isoformat(), "backend": backend, "seconds": seconds,
             "usd": round(cost, 4), "note": note}
        )
        self._save()
        return cost

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._ledger, indent=2) + "\n")
