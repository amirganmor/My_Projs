"""
Entity resolution and canonical ID generation.

Provides deterministic matching logic for:
  - player names  → canonical player_id
  - team names/abbreviations → canonical team_id
  - season strings → canonical season_id
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def normalize_name(name: str | None) -> str:
    """Lowercase, strip accents, remove suffixes, collapse whitespace."""
    if not name:
        return ""
    # Unicode → ASCII
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    # Remove common suffixes
    for suffix in [" jr.", " jr", " sr.", " sr", " iii", " ii", " iv"]:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    # Collapse whitespace and punctuation
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Canonical team abbreviation mapping (common variants)
TEAM_ABBR_MAP: dict[str, str] = {
    "NJN": "BKN", "NJ": "BKN", "BRK": "BKN",
    "NOH": "NOP", "NOK": "NOP", "NO": "NOP",
    "SEA": "OKC",
    "VAN": "MEM",
    "CHA": "CHO",  # Charlotte Bobcats → Hornets situation
    "CHH": "CHO",
    "WSB": "WAS", "WSH": "WAS",
    "PHO": "PHX",
    "SAN": "SAS", "SA": "SAS",
    "GS": "GSW",
    "NY": "NYK",
    "NO/OK": "NOP",
    "UTAH": "UTA",
}


def normalize_team_abbr(abbr: str | None) -> str:
    """Map variant team abbreviations to a canonical form."""
    if not abbr:
        return "UNK"
    canon = abbr.strip().upper()
    return TEAM_ABBR_MAP.get(canon, canon)


def normalize_season(season: str | None) -> str:
    """Ensure season is in 'YYYY-YY' format."""
    if not season:
        return ""
    s = str(season).strip()
    if re.match(r"^\d{4}-\d{2}$", s):
        return s
    if re.match(r"^\d{4}$", s):
        y = int(s)
        return f"{y}-{str(y + 1)[-2:]}"
    if re.match(r"^\d{4}-\d{4}$", s):
        parts = s.split("-")
        return f"{parts[0]}-{parts[1][-2:]}"
    return s


# ---------------------------------------------------------------------------
# Canonical ID generation
# ---------------------------------------------------------------------------

def make_player_id(nba_api_player_id: int | str | None) -> str:
    """Canonical player ID.  Uses NBA API numeric ID when available."""
    if nba_api_player_id and str(nba_api_player_id).strip():
        return f"P{int(nba_api_player_id)}"
    return ""


def make_player_id_from_name(name: str, team_abbr: str = "", season: str = "") -> str:
    """Fallback player ID from name hash (for sources without NBA API ID)."""
    key = f"{normalize_name(name)}|{normalize_team_abbr(team_abbr)}|{normalize_season(season)}"
    h = hashlib.md5(key.encode()).hexdigest()[:10]
    return f"PX{h}"


def make_team_id(nba_api_team_id: int | str | None) -> str:
    if nba_api_team_id and str(nba_api_team_id).strip() and str(nba_api_team_id) != "0":
        return f"T{int(nba_api_team_id)}"
    return ""


def make_team_id_from_abbr(abbr: str) -> str:
    canon = normalize_team_abbr(abbr)
    return f"TA{canon}"


def make_season_id(season: str) -> str:
    s = normalize_season(season)
    return f"S{s}" if s else ""


def make_game_id(nba_game_id: str | None) -> str:
    if nba_game_id:
        return f"G{str(nba_game_id).strip()}"
    return ""
