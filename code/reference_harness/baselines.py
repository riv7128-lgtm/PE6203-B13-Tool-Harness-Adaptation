"""Deterministic baselines over canonical tool knowledge.

Full rewrite means regenerating *all* canonical records from the current
snapshot. It does not claim an LLM rewrote free-form procedural memories.
"""
from copy import deepcopy


def no_update(old: dict, new: dict) -> dict:
    """Retain stale knowledge, even when its route no longer exists."""
    return deepcopy(old)


def full_rewrite(old: dict, new: dict) -> dict:
    """Regenerate the full normalized knowledge from the new snapshot."""
    return deepcopy(new)
