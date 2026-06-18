from __future__ import annotations

import re
from dataclasses import dataclass, field


_SYSTEM_RE = re.compile(
    r"\b(?:T\d{1,3}|SS\d{1,3}|UTA|EWC\d{1,3}|ELS\d{1,3}|POL-\d{1,3}|IP|PD)\b",
    re.IGNORECASE,
)
_AREA_RE = re.compile(r"\b(?:STF|STM|STA)\b", re.IGNORECASE)
_LEVEL_RE = re.compile(r"\b(?:L\d{1,2}|piano\s+\d{1,2})\b", re.IGNORECASE)
_LOCATION_RE = re.compile(
    r"\b(?:B\d+\s+V\d+|Torre\s+\d+|porta\s+\d{1,4}|COPERTURA\s+T\d+|Mandata|Ripresa)\b",
    re.IGNORECASE,
)
_COMPONENT_RE = re.compile(
    r"\b(?:plenum|vela|scarpetta|serranda|fancoil|canale|potenziometro|servomotore|montante)\b",
    re.IGNORECASE,
)
_TECH_CODE_RE = re.compile(r"\b[A-Z]{1,4}\d{1,4}\b|\b[A-Z]{1,4}-\d{1,4}\b|\b\d{1,3}[A-Z]\b")


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

    areas = primary_areas or _unique_matches(_AREA_RE, combined)
    systems = primary_systems or _unique_matches(_SYSTEM_RE, combined)
    levels = primary_levels or _unique_matches(_LEVEL_RE, combined)
    locations = primary_locations or _unique_matches(_LOCATION_RE, combined)
    components = _unique_matches(_COMPONENT_RE, combined)
    codes = _unique_matches(_TECH_CODE_RE, combined)

    return ExtractedContext(
        context_area=_first(areas),
        context_system=_first(systems),
        context_level=_first(levels),
        context_location=_first(locations),
        context_tags=_merge_tags(areas, systems, levels, locations, components, codes),
    )


def has_operational_context(context: ExtractedContext) -> bool:
    return bool(
        context.context_area
        or context.context_system
        or context.context_level
        or context.context_location
        or context.context_tags
    )
