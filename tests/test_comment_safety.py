"""Tests that reordering never silently reattaches a comment to the wrong definition.

libcst always attaches a comment to the statement that follows it. A comment glued
to the code *above* it (no blank line separating them) but written as a trailing
remark, not documentation of the following definition, can end up looking like it
describes an unrelated neighbour once that neighbour moves into its place. These
tests cover the one shape of that ambiguity this tool can resolve without
understanding what the comment means (blank-separated from what follows), and the
warning it raises for the shape it deliberately leaves alone (glued to both sides,
identical to the ordinary "comment documents the definition below it" convention).
"""

import libcst as cst
import pytest

from defsort.sorter import sort_file, sort_module_definitions

ORDER = ["public", "protected", "private"]


def sort_module_source(source: str, sort_mode: str = "alphabetical") -> str:
    """Sort module-level definitions in a source snippet.

    Args:
        source: The source code
        sort_mode: Either "minimize_movement" or "alphabetical"

    Returns:
        The sorted source code
    """
    module = cst.parse_module(source)
    new_module, _ = sort_module_definitions(module, ORDER, eager_annotations=True, sort_mode=sort_mode)
    return new_module.code


class TestUnambiguousTrailingComment:
    """A comment glued to the statement above but blank-separated from the next
    definition is protected: the definition it precedes, and the one it actually
    trails, are kept adjacent and neither moves.
    """

    def test_module_level_pair_stays_fused(self) -> None:
        """The commented definition and its predecessor do not get separated."""
        source = "def _b():\n    pass\n# note about _b above\n\ndef a():\n    pass\n"
        result = sort_module_source(source)
        assert result == source

    def test_unrelated_definitions_still_sort_around_the_pinned_pair(self) -> None:
        """Sorting elsewhere in the same run is unaffected by the pinned pair."""
        source = (
            "def z_pub():\n    pass\n\n"
            "def m_pub():\n    pass\n\n"
            "def _b():\n    pass\n# note about _b above\n\n"
            "def a_pub():\n    pass\n"
        )
        result = sort_module_source(source)
        assert result.index("def m_pub") < result.index("def z_pub")
        assert result.index("def _b") < result.index("# note about _b above") < result.index("def a_pub")

    def test_class_level_pair_stays_fused(self, tmp_path) -> None:  # noqa: ANN001
        """The same protection applies to methods inside a class body."""
        source = (
            "class Example:\n"
            "    def z(self):\n"
            "        pass\n\n"
            "    def _b(self):\n"
            "        pass\n"
            "    # note about _b above\n\n"
            "    def a(self):\n"
            "        pass\n"
        )
        target = tmp_path / "sample.py"
        target.write_text(source)

        sort_file(target, ORDER, sort_mode="alphabetical")
        result = target.read_text()
        assert result.index("def _b") < result.index("# note about _b above") < result.index("def a")

    def test_comment_at_start_of_run_touching_a_barrier_is_pinned_alone(self) -> None:
        """A comment glued to a barrier statement (not a sibling definition) pins
        just the definition after it -- there is no sibling to fuse it with, and
        the barrier itself never moves anyway.
        """
        source = "X = 1\n# note about X above\n\ndef z_pub():\n    pass\n\ndef a_pub():\n    pass\n"
        result = sort_module_source(source)
        assert result.index("X = 1") < result.index("# note about X above") < result.index("def z_pub")


class TestFullyAmbiguousCommentWarns:
    """A comment glued to both sides is left alone (matches the ordinary
    "comment documents the definition below it" convention), but reordering the
    group it's in now emits a warning so it can be checked by hand.
    """

    def test_warns_when_the_group_is_reordered(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Reordering a group containing a glued-both-sides comment warns."""
        source = "def _b():\n    pass\n# note about _b above\ndef a():\n    pass\n"
        sort_module_source(source)
        assert "'a' was reordered" in capsys.readouterr().out

    def test_no_warning_when_nothing_in_the_group_moves(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An already-sorted group with the same comment shape stays silent."""
        source = "def a():\n    pass\n# note about a above\ndef z():\n    pass\n"
        sort_module_source(source, sort_mode="minimize_movement")
        assert "was reordered" not in capsys.readouterr().out
