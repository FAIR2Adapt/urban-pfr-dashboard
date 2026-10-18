"""One composition run reads each object once through fdo-consume, with the contracts and profile maps the package ships."""
from __future__ import annotations

from .models import INFO, Diagnostic

OVERLAY = "cca-dashboard-additions"


class CompositionSession:
    """Consumptions of one run, keyed by (pid, contract). A profile is assumed only for a PID listed in
    `assumed_profiles`, and the assumption is recorded; an object that declares no profile is otherwise read as is."""

    def __init__(self, consume, recorded_dir: str, contracts: str | None = None, profile_maps: str | None = None,
                 overlay: str = OVERLAY, assumed_profiles: dict | None = None):
        self.consume = consume
        self.recorded_dir, self.contracts, self.profile_maps, self.overlay = recorded_dir, contracts, profile_maps, overlay
        self.assumed_profiles = dict(assumed_profiles or {})
        self.consumptions: dict = {}
        self.assumptions: dict = {}   # pid -> Diagnostic, once the assumption was used

    def consume_object(self, pid: str, contract: str):
        key = (pid, contract)
        if key not in self.consumptions:
            options = {"recorded_dir": self.recorded_dir, "contracts": self.contracts, "profile_maps": self.profile_maps,
                       "profile_overlay": self.overlay}
            assumed = self.assumed_profiles.get(pid)
            if assumed:
                options["profile"] = assumed
                self.assumptions.setdefault(pid, Diagnostic("object.profile_assumed", INFO,
                                                            f"{pid} is read with the profile map {assumed} by this consumer's configuration"))
            self.consumptions[key] = self.consume(pid, contract, **options)
        return self.consumptions[key]

    def binding_of(self, pid: str):
        """The binding of a PID read in this run under any contract, else None."""
        return next((c.binding for (p, _), c in self.consumptions.items() if p == pid and c.binding is not None), None)

    def crate_hashes(self) -> dict:
        return {pid: c.record.crate_sha256 for (pid, _), c in self.consumptions.items() if c.record.crate_sha256}
