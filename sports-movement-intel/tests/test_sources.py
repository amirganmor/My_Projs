"""Source-layer safety and contract tests (SYNTHETIC archives/records only)."""

import zipfile

import pytest

from smip.contracts.models import Envelope
from smip.features.basketball import COURT_L, in_corner, in_paint, spacing_hook
from smip.sources.fetch import parse_lfs_pointer
from smip.sources.safe_extract import extract_zip


def _zip(tmp_path, members):
    p = tmp_path / "a.zip"
    with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return p


def test_zip_path_traversal_rejected(tmp_path):
    p = _zip(tmp_path, {"../evil.txt": "x"})
    with pytest.raises(Exception):
        extract_zip(p, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_zip_absolute_path_rejected(tmp_path):
    p = _zip(tmp_path, {"/etc/evil": "x"})
    with pytest.raises(Exception):
        extract_zip(p, tmp_path / "out")


def test_zip_ok(tmp_path):
    p = _zip(tmp_path, {"d/ok.json": "{}"})
    extract_zip(p, tmp_path / "out")
    assert (tmp_path / "out" / "d" / "ok.json").read_text() == "{}"


def test_zip_bomb_ratio_rejected(tmp_path):
    p = _zip(tmp_path, {"big.txt": "0" * 50_000_000})
    with pytest.raises(Exception):
        extract_zip(p, tmp_path / "out")


def test_lfs_pointer_parse():
    ptr = b"version https://git-lfs.github.com/spec/v1\noid sha256:abc123\nsize 42\n"
    assert parse_lfs_pointer(ptr) == {"oid": "abc123", "size": 42}
    assert parse_lfs_pointer(b"{}") is None


def _env(**kw):
    base = dict(schema_version="1.0.0", record_type="tracking_frame", source="synthetic", source_revision="r",
                sport="soccer", match_id="synthetic:m", record_id="x", replay_session_id="s", sequence=1,
                replay_event_time="2026-01-01T00:00:00Z", produced_at="2026-01-01T00:00:00Z")
    base.update(kw)
    return Envelope(**base)


def test_envelope_rejects_unknown_quality_flag():
    with pytest.raises(Exception):
        _env(quality_flags=["made_up_flag"])
    assert _env(quality_flags=["injected_duplicate"]).quality_flags == ["injected_duplicate"]


def test_court_regions():
    rim_x = COURT_L / 2 - 1.6
    assert in_paint(rim_x, 0.0)
    assert not in_paint(0.0, 0.0)
    assert in_corner(COURT_L / 2 - 1.0, 7.0)
    assert not in_corner(COURT_L / 2 - 1.0, 3.0)


def test_spacing_hook_offense_and_defense():
    off = [("a", 12.0, 0.0, True), ("b", 13.0, 7.2, True), ("c", 5.0, -3.0, True)]
    fr = {"poss": "T1", "ents": [[None, "ball", None, 0.0, 0.0, None, None, None, True, "observed"],
                                 ["d1", "player", "T2", 1.0, 0.0, None, None, None, True, "observed"],
                                 ["d2", "player", "T2", 3.0, 4.0, None, None, None, True, "observed"]]}
    r = spacing_hook(fr, "T1", off, None)
    assert r["offense"] is True and r["paint_count"] == 1 and r["corner_count"] == 1
    d = spacing_hook(fr, "T2", [("d1", -1.0, 0.0, True), ("d2", -3.0, -4.0, True)], None)
    assert d["offense"] is False and d["nearest_def_to_ball_m"] == pytest.approx(1.0)
