"""Tests for the policy packs catalog."""

from __future__ import annotations

from agent_tooltrust.cli.pack import list_packs


class TestListPacks:
    def test_lists_five_or_more_packs(self) -> None:
        packs = list_packs()
        assert len(packs) >= 5, f"Expected 5+ packs, got {len(packs)}"

    def test_each_pack_has_required_fields(self) -> None:
        packs = list_packs()
        for p in packs:
            assert "name" in p, f"Pack missing name: {p}"
            assert "domains" in p
            assert "tool_count" in p
            assert "tests_passing" in p
            assert "last_updated" in p

    def test_pack_list_includes_db_queries(self) -> None:
        names = {p["name"] for p in list_packs()}
        assert "db-queries" in names


class TestPackCLI:
    def test_pack_list_runs(self) -> None:
        from agent_tooltrust.cli import main

        rc = main(["pack", "list"])
        assert rc == 0

    def test_pack_info_runs(self) -> None:
        from agent_tooltrust.cli import main

        rc = main(["pack", "info", "db-queries"])
        assert rc == 0

    def test_pack_info_not_found(self) -> None:
        from agent_tooltrust.cli import main

        rc = main(["pack", "info", "nonexistent-pack"])
        assert rc == 1
