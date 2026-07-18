"""Tests for entity resolution and ID generation."""
import pytest
from jobs.common.ids import (
    normalize_name,
    normalize_team_abbr,
    normalize_season,
    make_player_id,
    make_player_id_from_name,
    make_team_id,
    make_season_id,
)


class TestNormalizeName:
    def test_basic(self):
        assert normalize_name("LeBron James") == "lebron james"

    def test_suffix_jr(self):
        assert normalize_name("Tim Hardaway Jr.") == "tim hardaway"

    def test_suffix_iii(self):
        assert normalize_name("Wendell Carter III") == "wendell carter"

    def test_accents(self):
        assert normalize_name("Nikola Jokić") == "nikola jokic"

    def test_none(self):
        assert normalize_name(None) == ""

    def test_extra_whitespace(self):
        assert normalize_name("  Stephen   Curry  ") == "stephen curry"


class TestNormalizeTeamAbbr:
    def test_standard(self):
        assert normalize_team_abbr("LAL") == "LAL"

    def test_variant_nets(self):
        assert normalize_team_abbr("NJN") == "BKN"

    def test_variant_brooklyn(self):
        assert normalize_team_abbr("BRK") == "BKN"

    def test_variant_nola(self):
        assert normalize_team_abbr("NOH") == "NOP"

    def test_supersonics(self):
        assert normalize_team_abbr("SEA") == "OKC"

    def test_none(self):
        assert normalize_team_abbr(None) == "UNK"


class TestNormalizeSeason:
    def test_standard(self):
        assert normalize_season("2023-24") == "2023-24"

    def test_year_only(self):
        assert normalize_season("2023") == "2023-24"

    def test_full_year_range(self):
        assert normalize_season("2023-2024") == "2023-24"


class TestMakeIds:
    def test_player_id(self):
        assert make_player_id(201566) == "P201566"

    def test_player_id_string(self):
        assert make_player_id("201566") == "P201566"

    def test_player_id_from_name(self):
        pid = make_player_id_from_name("LeBron James", "LAL", "2023-24")
        assert pid.startswith("PX")
        assert len(pid) == 12

    def test_team_id(self):
        assert make_team_id(1610612747) == "T1610612747"

    def test_season_id(self):
        assert make_season_id("2023-24") == "S2023-24"
