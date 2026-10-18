"""Binding policy: a plugin's inputs against the entities of one target. The default policy matches propertyIDs
exactly and decides by count (0: FAIL, 1: bind, more: INDETERMINATE); it never guesses between equivalent candidates.
Access is reported beside the composition status, never in its place."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..services.formats import canonical
from .models import (ERROR, FAIL, INDETERMINATE, INFO, OPEN, PARTIAL, PASS, RESTRICTED, UNKNOWN, WARNING, Diagnostic,
                     InputBinding, worse)

# input kind (additionalType of the FormalParameter) -> entity types or canonical concepts it accepts
KINDS = {"Claim": ("Claim", "Assertion")}
OBJECT_KIND = "Object"   # the consumed object itself, for a plugin that shows the whole FDO (metadata card)


@dataclass
class BindingResult:
    inputs: list = field(default_factory=list)        # InputBinding, in declared order
    status: str = PASS                                # composition: PASS | PARTIAL | FAIL | INDETERMINATE
    access: str = OPEN                                # open | restricted | unknown, from the required inputs
    diagnostics: list = field(default_factory=list)   # Diagnostic
    decisions: list = field(default_factory=list)     # one line per bound input, for the evidence

    def add(self, code: str, level: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(code, level, message))


class BindingPolicy(Protocol):
    def bind(self, plugin_binding: dict, target_binding: dict, fragment: str | None) -> BindingResult: ...


def _short(kind: str | None) -> str:
    return (kind or "").split(":")[-1].split("/")[-1]


def _access_state(entity: dict) -> str:
    """Access of a product whose files a panel serves: open only when declared open; an absent statement is unknown."""
    state = (entity.get("access") or {}).get("state")
    return OPEN if state == "open" else RESTRICTED if state == "restricted" else UNKNOWN


def _described_access(states: list) -> str:
    """Access of text that is part of the description already read (the object's fields, its claims): shown unless declared
    restricted. No file is served for it."""
    return RESTRICTED if "restricted" in states else OPEN


def _flag(value):
    """A declared boolean: True or False, also as the strings true and false; None for anything else."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


class EntityIndex:
    """{(holder, type): [entities]} of one binding, built once; the fdo-consume binding itself is not written to."""

    def __init__(self, binding: dict):
        self.binding = binding
        self.held: dict = {}
        for entity in binding["entities"]:
            for holder in entity["holders"]:
                self.held.setdefault((holder, entity["type"]), []).append(entity)

    def entities_held_by(self, holder: str, entity_type: str) -> list:
        return self.held.get((holder, entity_type), [])

    def of_type(self, entity_type: str) -> list:
        return [e for e in self.binding["entities"] if e["type"] == entity_type]


def plugin_inputs(plugin: EntityIndex) -> list:
    """[(input entity, [(variable name, propertyID)])] in the plugin's declared order."""
    found = []
    for entity in plugin.of_type("Input"):
        variables = [(v["fields"].get("name"), v["fields"].get("property_id")) for v in plugin.entities_held_by(entity["id"], "Variable")]
        found.append((entity, variables))
    return found


def _matches_input_kind(entity: dict, kind: str) -> bool:
    accepted = KINDS.get(_short(kind), (_short(kind),))
    return entity["type"] in accepted or any(c in accepted for c in entity.get("provides", []))


def candidate_entities(target: EntityIndex, fragment: str | None, kind: str) -> list:
    """The fragment's entity when one is named, else every entity of the input's kind."""
    if fragment:
        return [e for e in target.binding["entities"] if e["id"] == "#" + fragment]
    return [e for e in target.binding["entities"] if _matches_input_kind(e, kind)]


def _match_required_variables(target: EntityIndex, entity: dict, variables: list) -> tuple[dict, list, list]:
    """{variable name: column} for the variables found exactly once on the entity; the missing; the ambiguous."""
    held = target.entities_held_by(entity["id"], "Variable")
    bound, missing, ambiguous = {}, [], []
    for name, iri in variables:
        hits = [v for v in held if v["fields"].get("property_id") == iri]
        if len(hits) == 1:
            bound[name] = hits[0]["fields"].get("name")
        elif not hits:
            missing.append(iri)
        else:
            ambiguous.append(iri)
    return bound, missing, ambiguous


class ExactSemanticBinder:
    """Exact propertyID matching; equal candidates are reported, never ranked."""

    def bind(self, plugin_binding: dict, target_binding: dict, fragment: str | None) -> BindingResult:
        plugin, target = EntityIndex(plugin_binding), EntityIndex(target_binding)
        result = BindingResult()
        declared = plugin_inputs(plugin)
        names = [entity["fields"].get("name") for entity, _ in declared]
        repeated = sorted({n for n in names if names.count(n) > 1})
        if repeated:
            result.add("plugin.duplicate_input", ERROR, f"the plugin declares the input name(s) {repeated} more than once; nothing was bound")
            result.status = FAIL
            return result
        for entity, variables in declared:
            self._bind_input(entity, variables, target, fragment, result)
        required = [i for i in result.inputs if i.required]
        result.access = (RESTRICTED if any(i.access == RESTRICTED for i in required)
                         else UNKNOWN if any(i.access == UNKNOWN for i in required) else OPEN)
        return result

    def _bind_input(self, entity: dict, variables: list, target: EntityIndex, fragment: str | None, result: BindingResult) -> None:
        fields = entity["fields"]
        name, kind = fields.get("name"), fields.get("kind")
        declared_required = fields.get("required")
        required = True if declared_required is None else _flag(declared_required)
        if required is None:
            result.add("plugin.input_required_unreadable", WARNING,
                       f"input {name}: valueRequired {declared_required!r} is not true or false; the input is treated as required")
            required = True
        raw_formats = fields.get("formats") or []
        raw_formats = raw_formats if isinstance(raw_formats, list) else [raw_formats]
        formats = [m.lower() for m in raw_formats if isinstance(m, str)]
        if len(formats) != len(raw_formats):
            result.add("plugin.input_format_unreadable", WARNING, f"input {name}: an accepted format that is not text is ignored")
        label = "input" if required else "optional input"
        if not isinstance(name, str) or not name.strip() or not isinstance(kind, str) or not kind.strip():
            result.add("plugin.input_incomplete", ERROR if required else WARNING,
                       f"{label} {entity['id']}: an input needs a name and a kind to be bound")
            result.status = worse(result.status, FAIL if required else PARTIAL)
            return

        def lower(status: str) -> None:   # a required input decides; an optional one only lowers PASS to PARTIAL
            result.status = worse(result.status, status if required else PARTIAL)

        if _short(kind) == OBJECT_KIND:   # the whole object, declared as such; nothing is selected or invented
            obj = target.binding["object"]   # its description was read; only a declared restriction on the object itself counts
            result.inputs.append(InputBinding(name, "./", OBJECT_KIND, {}, required, formats,
                                              _described_access([(obj.get("access") or {}).get("state")])))
            result.decisions.append(f"{entity['id']}: the object {obj['pid']}")
            return
        pool = candidate_entities(target, fragment, kind)
        if fragment and not pool:
            result.add("bind.fragment_missing", ERROR, f"{label} {name}: the target has no entity #{fragment}")
            lower(FAIL)
            return
        wrong = [e for e in pool if not _matches_input_kind(e, kind)]
        if fragment and wrong:
            result.add("bind.kind_mismatch", ERROR, f"{label} {name}: #{fragment} is a {wrong[0]['type']}, the input takes {kind}")
            lower(FAIL)
            return
        if variables:
            chosen = self._by_variables(name, label, required, variables, pool, target, result, lower)
        elif _short(kind) == "Claim" and pool:
            chosen = None
            result.inputs.append(InputBinding(name, [e["id"] for e in pool], "Claim", {}, required, formats,
                                              _described_access([(e.get("access") or {}).get("state") for e in pool])))
            result.decisions.append(f"{entity['id']}: {len(pool)} claims")
            return
        else:
            chosen = self._by_count(name, label, kind, required, pool, result, lower)
        if chosen is None:
            return
        binding = InputBinding(name, chosen[0]["id"], chosen[0]["type"], chosen[1], required, formats, _access_state(chosen[0]))
        result.inputs.append(binding)
        result.decisions.append(f"{entity['id']}: {chosen[0]['id']}" + (f" provides {sorted(chosen[1])}" if chosen[1] else ""))
        if formats and chosen[0]["type"] == "Dataset":
            wanted = {canonical(f) for f in formats} - {None}
            served = [r for r in target.binding["resources"] if chosen[0]["id"] in r["holders"] and canonical(r["media_type"]) in wanted]
            if not served:
                result.add("bind.no_format", ERROR if required else WARNING,
                           f"{label} {name}: {chosen[0]['id']} has no distribution in an accepted format {formats}")
                lower(FAIL)
        if binding.access == RESTRICTED:
            result.add("bind.restricted", INFO, f"{label} {name}: {chosen[0]['id']} is restricted; listed, not served")

    def _by_variables(self, name, label, required, variables, pool, target, result, lower):
        covering, ambiguous_in = [], []
        for candidate in pool:
            bound, missing, ambiguous = _match_required_variables(target, candidate, variables)
            if ambiguous:
                ambiguous_in.append((candidate, ambiguous))
            elif not missing:
                covering.append((candidate, bound))
        if len(covering) == 1 and not ambiguous_in:
            unnamed = sorted(var for var, column in covering[0][1].items() if not column)
            if unnamed:   # a matched variable must also name the column the renderer reads
                result.add("bind.no_column", ERROR if required else WARNING,
                           f"{label} {name}: {covering[0][0]['id']} declares {unnamed} without a column name")
                lower(FAIL)
                return None
            return covering[0]
        if ambiguous_in or len(covering) > 1:
            who = [c["id"] for c, _ in (ambiguous_in or covering)]
            what = "variables with the same propertyID" if ambiguous_in else "entities that provide every required variable"
            result.add("bind.ambiguous", ERROR if required else WARNING, f"{label} {name}: {len(who)} {what}: {', '.join(who)}; not decided")
            lower(INDETERMINATE)
            return None
        have = {v["fields"].get("property_id") for c in pool for v in target.entities_held_by(c["id"], "Variable")}
        lacking = [iri.rsplit("/", 1)[-1] for _, iri in variables if iri not in have]
        if required:
            result.add("bind.no_candidate", ERROR, f"input {name}: no entity provides the required variables {lacking}")
            lower(FAIL)
        else:
            result.add("bind.optional_missing", WARNING, f"optional input {name}: variables {lacking} not provided")
            lower(PARTIAL)
        return None

    def _by_count(self, name, label, kind, required, pool, result, lower):
        if len(pool) == 1:
            return pool[0], {}
        if not pool:
            if required:
                result.add("bind.no_candidate", ERROR, f"input {name}: the target has no {kind}")
                lower(FAIL)
            else:
                result.add("bind.optional_missing", WARNING, f"optional input {name}: the target has no {kind}")
                lower(PARTIAL)
            return None
        result.add("bind.ambiguous", ERROR if required else WARNING, f"{label} {name}: {len(pool)} entities of kind {kind}; not decided")
        lower(INDETERMINATE)
        return None
