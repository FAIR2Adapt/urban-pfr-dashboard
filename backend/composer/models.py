"""The plan: one dashboard after every reference was resolved; plain data with a published shape.

Three separate dimensions, never collapsed into one flag:
- composition status of a panel or plan: PASS, PARTIAL, FAIL, INDETERMINATE;
- access state of what a panel binds: open, restricted, unknown;
- renderer compatibility of the local implementation: PASS, FAIL, INDETERMINATE (RendererBinding.status).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

DASHBOARD_PLAN_SCHEMA_ID = "fdo-dashboard-plan/2"   # a change of meaning in the serialized shape is a new number

PASS, PARTIAL, FAIL, INDETERMINATE = "PASS", "PARTIAL", "FAIL", "INDETERMINATE"
CompositionStatus = Literal["PASS", "PARTIAL", "FAIL", "INDETERMINATE"]
USABLE = (PASS, PARTIAL)
SEVERITY = {PASS: 0, PARTIAL: 1, INDETERMINATE: 2, FAIL: 3}

OPEN, RESTRICTED, UNKNOWN = "open", "restricted", "unknown"
AccessState = Literal["open", "restricted", "unknown"]

INFO, WARNING, ERROR = "info", "warning", "error"
Level = Literal["info", "warning", "error"]


def worse(current: str, new: str) -> str:
    """The more severe of two composition statuses; a FAIL is never overwritten by a lesser one."""
    return new if SEVERITY[new] > SEVERITY[current] else current


@dataclass
class Diagnostic:
    code: str          # fixed, for programs: <area>.<name>
    level: Level       # info | warning | error
    message: str       # one-sentence summary for display

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PluginReference:
    pid: str
    version: str | None = None   # softwareVersion as the Plugin FDO declares it
    kind: str | None = None      # additionalType: data adapter, view panel
    name: str | None = None


@dataclass
class TargetReference:
    """What the panel's `object` names: a PID, optionally one entity of it."""
    pid: str | None
    fragment: str | None = None


@dataclass
class RendererBinding:
    """The trusted local implementation chosen for a plugin, and whether it may run for the declared version."""
    renderer_id: str
    supported_plugin_version: str
    channels: dict = field(default_factory=dict)
    palettes: list = field(default_factory=list)
    status: str = PASS   # compatibility: PASS (exact version), FAIL (another version), INDETERMINATE (none declared)


@dataclass
class InputBinding:
    """One plugin input bound to one target entity (or, for claims, a list of entities)."""
    name: str
    entity: str | list
    kind: str
    variables: dict = field(default_factory=dict)   # input variable name -> column of the target
    required: bool = True
    formats: list = field(default_factory=list)     # media types the plugin reads, lower case
    access: AccessState = OPEN


@dataclass
class PanelPlan:
    id: str
    name: str | None
    plugin: PluginReference
    target: TargetReference
    renderer: RendererBinding | None = None
    inputs: list = field(default_factory=list)      # InputBinding, in the plugin's declared order
    settings: dict = field(default_factory=dict)    # plugin defaults overlaid by the panel's declared values
    position: int | None = None
    status: CompositionStatus = PASS
    access: AccessState = OPEN
    diagnostics: list = field(default_factory=list)   # Diagnostic
    evidence: dict = field(default_factory=dict)      # crate hashes read, binding decisions, formats

    def add(self, code: str, level: Level, message: str) -> None:
        self.diagnostics.append(Diagnostic(code, level, message))

    def fail(self, code: str, message: str) -> None:
        self.add(code, ERROR, message)
        self.status = worse(self.status, FAIL)

    @property
    def codes(self) -> list:
        return [d.code for d in self.diagnostics]

    def input(self, name: str):
        return next((i for i in self.inputs if i.name == name), None)

    @property
    def drawable(self) -> bool:
        """Composed, implemented for the declared version, and open: what a renderer may be given."""
        return self.status in USABLE and self.renderer is not None and self.renderer.status == PASS and self.access == OPEN

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "plugin": asdict(self.plugin),
                "renderer": None if self.renderer is None else asdict(self.renderer),
                "object": asdict(self.target),                       # the profile's term for what a panel shows
                "inputs": [asdict(i) for i in self.inputs], "settings": self.settings, "position": self.position,
                "status": self.status, "access": self.access, "diagnostics": [d.to_dict() for d in self.diagnostics],
                "evidence": self.evidence}


@dataclass
class DashboardPlan:
    pid: str
    title: str | None
    subject_pid: str | None                         # the Dashboard's `about`
    status: CompositionStatus
    panels: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)   # Diagnostic
    evidence: dict = field(default_factory=dict)      # crate hash, map, overlay, every object read with its hash
    uncomposed_parts: list = field(default_factory=list)

    def add(self, code: str, level: Level, message: str) -> None:
        self.diagnostics.append(Diagnostic(code, level, message))

    @property
    def usable_panels(self) -> list:
        return [p for p in self.panels if p.status in USABLE]

    @property
    def drawable_panels(self) -> list:
        return [p for p in self.panels if p.drawable]

    def to_dict(self) -> dict:
        return {"schema": DASHBOARD_PLAN_SCHEMA_ID, "pid": self.pid, "title": self.title, "about": self.subject_pid,
                "status": self.status, "panels": [p.to_dict() for p in self.panels],
                "diagnostics": [d.to_dict() for d in self.diagnostics], "evidence": self.evidence,
                "uncomposed_parts": self.uncomposed_parts}
