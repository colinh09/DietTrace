"""Per-user macro preference memory (macro-learning closure, phase 1).

The split is derived only from the saved targets (profile-free), is scale-free
(fractions of kcal), is per-user isolated, and the latest save wins.
"""

from __future__ import annotations

from dietrace.web.macro_memory import SqliteMacroMemory, split_of


def test_split_of_derives_fractions_from_targets() -> None:
    # 2000 kcal, 150 g protein (30%), 67 g fat (~30%).
    split = split_of({"208": 2000.0, "203": 150.0, "204": 67.0, "205": 200.0})
    assert split is not None
    assert split["protein_pct"] == 0.3
    assert round(split["fat_pct"], 2) == 0.3


def test_split_of_none_when_no_kcal() -> None:
    assert split_of({"208": 0.0, "203": 150.0, "204": 67.0}) is None
    assert split_of({"203": 150.0}) is None


def test_remember_and_recall_round_trip(tmp_path) -> None:
    mem = SqliteMacroMemory(tmp_path / "macro_mem.sqlite")
    assert mem.recall("alice") is None
    stored = mem.remember("alice", {"208": 2000.0, "203": 200.0, "204": 56.0})
    assert stored is True
    pref = mem.recall("alice")
    assert pref is not None
    assert pref["protein_pct"] == 0.4  # 200 g * 4 / 2000
    assert mem.count("alice") == 1


def test_remember_skips_when_no_kcal(tmp_path) -> None:
    mem = SqliteMacroMemory(tmp_path / "macro_mem.sqlite")
    assert mem.remember("alice", {"203": 150.0}) is False
    assert mem.recall("alice") is None


def test_per_user_isolation(tmp_path) -> None:
    mem = SqliteMacroMemory(tmp_path / "macro_mem.sqlite")
    mem.remember("alice", {"208": 2000.0, "203": 200.0, "204": 56.0})
    mem.remember("bob", {"208": 2500.0, "203": 150.0, "204": 90.0})
    assert mem.recall("alice")["protein_pct"] == 0.4
    assert mem.recall("bob")["protein_pct"] == 0.24
    assert mem.recall("carol") is None


def test_latest_save_wins(tmp_path) -> None:
    mem = SqliteMacroMemory(tmp_path / "macro_mem.sqlite")
    mem.remember("alice", {"208": 2000.0, "203": 150.0, "204": 67.0})
    mem.remember("alice", {"208": 2000.0, "203": 200.0, "204": 56.0})
    assert mem.recall("alice")["protein_pct"] == 0.4
    assert mem.count("alice") == 1
