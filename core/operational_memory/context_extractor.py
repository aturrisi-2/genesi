from __future__ import annotations

import re
from dataclasses import dataclass, field


_SYSTEM_RE = re.compile(
    r"\b(?:T\d{1,3}|SS\d{1,3}|UTA|EWC\d{1,3}|ELS\d{1,3}|POL-\d{1,3}|IP|PD)\b",
    re.IGNORECASE,
)
_AREA_RE = re.compile(r"\b(?:STF|STM|STA)\b", re.IGNORECASE)
# B11: level ranges ("L3-7", "L3-L7", "DA L3 A L7") + piano/livello phrasing.
_LEVEL_RE = re.compile(
    r"\b(?:L\d{1,2}(?:\s*[-–]\s*L?\d{1,2})?|(?:piano|livello)\s+\d{1,2})\b",
    re.IGNORECASE,
)
# B11: scala (stairwell) — "SCALA 2" / "SC03".
_SCALA_RE = re.compile(r"\b(?:scala\s*\d{1,2}|SC\d{1,2})\b", re.IGNORECASE)
# B11: technical rooms/locations without digits (CED, centrale <x>, locale tecnico, …).
_LOCATION_RE = re.compile(
    r"\b(?:B\d+\s+V\d+|Torre\s+\d+|porta\s+\d{1,4}|COPERTURA\s+T\d+|Mandata|Ripresa|"
    r"CED|centrale\s+[A-Za-z]\w*|locale\s+tecnico|garage|copertura|cavedio)\b",
    re.IGNORECASE,
)
_COMPONENT_RE = re.compile(
    r"\b(?:plenum|vela|scarpetta|serranda|fancoil|canale|potenziometro|servomotore|montante)\b",
    re.IGNORECASE,
)
_TECH_CODE_RE = re.compile(r"\b[A-Z]{1,4}\d{1,4}\b|\b[A-Z]{1,4}-\d{1,4}\b|\b\d{1,3}[A-Z]\b")

_LEVEL_RANGE_RE = re.compile(r"^L?(\d{1,2})\s*[-–]\s*L?(\d{1,2})$", re.IGNORECASE)


def normalize_context_token(value: str) -> str:
    """Canonical spatial key for grouping/matching — generic, no site vocabulary:
    'Torre 2'→'T2', 'piano 5'/'livello 5'→'L5', 'SC3'→'SCALA 3',
    'L3-7'→'L3-L7', everything uppercased with collapsed spaces."""
    v = re.sub(r"\s+", " ", (value or "").strip()).upper()
    m = re.match(r"^TORRE\s*(\d+)$", v)
    if m:
        return f"T{m.group(1)}"
    m = re.match(r"^(?:PIANO|LIVELLO)\s*(\d+)$", v)
    if m:
        return f"L{int(m.group(1))}"
    m = re.match(r"^L(\d+)$", v)
    if m:
        return f"L{int(m.group(1))}"
    m = re.match(r"^SC(?:ALA)?\s*(\d+)$", v)
    if m:
        return f"SCALA {m.group(1)}"
    m = _LEVEL_RANGE_RE.match(v)
    if m:
        return f"L{int(m.group(1))}-L{int(m.group(2))}"
    return v


def expand_level_range(value: str) -> list[str]:
    """'L3-7' / 'L3-L7' → ['L3','L4','L5','L6','L7'] so every level in the range
    is individually matchable. Non-range values pass through unchanged."""
    m = _LEVEL_RANGE_RE.match(re.sub(r"\s+", "", value or ""))
    if not m:
        return [value] if value else []
    lo, hi = int(m.group(1)), int(m.group(2))
    if lo > hi or hi - lo > 30:
        return [value]
    return [f"L{n}" for n in range(lo, hi + 1)]


@dataclass
class ExtractedContext:
    context_area: str | None = None
    context_system: str | None = None
    context_level: str | None = None
    context_location: str | None = None
    context_tags: list[str] = field(default_factory=list)


def _unique_matches(pattern: re.Pattern, text: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(text or ""):
        value = re.sub(r"\s+", " ", match.group(0)).strip()
        key = value.upper()
        if key in seen:
            continue
        seen.add(key)
        values.append(value)
    return values


def _first(values: list[str]) -> str | None:
    return values[0] if values else None


def _merge_tags(*groups: list[str]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            key = value.upper()
            if key in seen:
                continue
            seen.add(key)
            tags.append(value)
    return tags


def extract_context(text: str, nearby_texts: list[str] | None = None) -> ExtractedContext:
    nearby_texts = nearby_texts or []
    combined = "\n".join([text or "", *nearby_texts])
    primary = text or ""

    primary_areas = _unique_matches(_AREA_RE, primary)
    primary_systems = _unique_matches(_SYSTEM_RE, primary)
    primary_levels = _unique_matches(_LEVEL_RE, primary)
    primary_locations = _unique_matches(_LOCATION_RE, primary)
    primary_scala = _unique_matches(_SCALA_RE, primary)

    areas = primary_areas or _unique_matches(_AREA_RE, combined)
    systems = primary_systems or _unique_matches(_SYSTEM_RE, combined)
    levels = primary_levels or _unique_matches(_LEVEL_RE, combined)
    locations = primary_locations or _unique_matches(_LOCATION_RE, combined)
    scala = primary_scala or _unique_matches(_SCALA_RE, combined)
    components = _unique_matches(_COMPONENT_RE, combined)
    codes = _unique_matches(_TECH_CODE_RE, combined)

    # B11: canonical aliases in tags so both raw and normalised forms match
    # ("Torre 2"→T2, "piano 5"→L5, "SC3"→SCALA 3, "L3-7"→L3…L7 expanded).
    norm_tags: list[str] = []
    for group in (areas, systems, levels, locations, scala):
        for value in group:
            canon = normalize_context_token(value)
            if canon and canon != value.upper():
                norm_tags.append(canon)
    for value in levels:
        for lv in expand_level_range(normalize_context_token(value)):
            norm_tags.append(lv)

    # scala counts as a location when no other location was found.
    location = _first(locations) or (_first(scala))

    return ExtractedContext(
        context_area=_first(areas),
        context_system=_first(systems),
        context_level=_first(levels),
        context_location=location,
        context_tags=_merge_tags(areas, systems, levels, locations, scala,
                                 components, codes, norm_tags),
    )


def has_operational_context(context: ExtractedContext) -> bool:
    return bool(
        context.context_area
        or context.context_system
        or context.context_level
        or context.context_location
        or context.context_tags
    )
