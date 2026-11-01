"""התאמת שכבות לפרופיל התצוגה (knowledge/layer_profile.yaml)."""
from __future__ import annotations

import fnmatch
import os

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.join(HERE, "..", "knowledge")


def load(name="default", path=None):
    path = path or os.path.join(KNOWLEDGE, "layer_profile.yaml")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)[name]


def _any(pats, layer):
    return any(fnmatch.fnmatch(layer.lower(), p.lower()) for p in pats)


def classify(layer, profile):
    """מחזיר 'lighting' / 'show' / 'hide'. hide הוא ברירת המחדל."""
    if _any(profile.get("lighting", []), layer):
        return "lighting"
    if _any(profile.get("hide", []), layer):
        return "hide"
    if _any(profile.get("show", []), layer):
        return "show"
    return profile.get("fallback", "hide")


def split(layers, profile):
    out = {"show": [], "hide": [], "lighting": []}
    for l in layers:
        out[classify(l, profile)].append(l)
    return out
