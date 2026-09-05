"""Lightweight consensus filtering shared by DrumScribe model runners."""

from __future__ import annotations

from typing import Any


def apply_low_confidence_consensus_gate(
    hits: list[Any],
    articulation: list[Any],
    rules: dict[str, Any] | None,
) -> tuple[list[Any], dict[str, Any]]:
    """Reject weak family hits unless the independent articulation model agrees."""
    if not rules or rules.get("enabled") is not True:
        return hits, {
            "lowConfidenceConsensusGate": False,
            "lowConfidenceConsensusRemoved": {},
        }
    family_rules = {
        str(family): {
            "minimumConfidence": float(family_rule["minimumConfidence"]),
            "matchSeconds": float(family_rule["matchSeconds"]),
        }
        for family, family_rule in rules["familyRules"].items()
    }
    families = set(family_rules)
    removed: dict[str, int] = {family: 0 for family in sorted(families)}
    retained: list[Any] = []
    for hit in hits:
        family_rule = family_rules.get(hit.family)
        if family_rule is None:
            retained.append(hit)
            continue
        supported = hit.confidence >= family_rule["minimumConfidence"] or any(
            candidate.family == hit.family
            and abs(candidate.onset - hit.onset) <= family_rule["matchSeconds"]
            for candidate in articulation
        )
        if supported:
            retained.append(hit)
        else:
            removed[hit.family] += 1
    return retained, {
        "lowConfidenceConsensusGate": True,
        "lowConfidenceConsensusFamilyRules": family_rules,
        "lowConfidenceConsensusRemoved": removed,
    }
