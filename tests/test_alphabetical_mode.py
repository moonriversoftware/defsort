"""Tests for the 'alphabetical' sort_mode, as opposed to the default 'minimize_movement'."""

from pathlib import Path

import libcst as cst

from undersort.sorter import sort_file, sort_module_definitions

ORDER = ["public", "protected", "private"]


def sort_module_source(source: str, sort_mode: str = "alphabetical", order: list[str] | None = None) -> str:
    """Sort module-level definitions in a source snippet under the given mode.

    Args:
        source: The source code
        sort_mode: Either "minimize_movement" or "alphabetical"
        order: Visibility ordering, defaults to public/protected/private

    Returns:
        The sorted source code
    """
    module = cst.parse_module(source)
    new_module, _ = sort_module_definitions(module, order or ORDER, eager_annotations=True, sort_mode=sort_mode)
    return new_module.code


def definition_names(source: str) -> list[str]:
    """List top-level definition names in order of appearance.

    Args:
        source: The source code

    Returns:
        The definition names
    """
    module = cst.parse_module(source)
    return [statement.name.value for statement in module.body if isinstance(statement, (cst.FunctionDef, cst.ClassDef))]


class TestAlphabeticalModuleSorting:
    """Tests for alphabetizing module-level definitions within each visibility group."""

    def test_definitions_alphabetized_within_group(self) -> None:
        """Same-group definitions are ordered by name, ignoring original position."""
        source = "def z_public():\n    pass\n\ndef a_public():\n    pass\n\ndef m_public():\n    pass\n"
        assert definition_names(sort_module_source(source)) == ["a_public", "m_public", "z_public"]

    def test_groups_still_take_priority_over_name(self) -> None:
        """Visibility group ordering still wins over alphabetical order across groups."""
        source = "def z_public():\n    pass\n\ndef _a_protected():\n    pass\n"
        assert definition_names(sort_module_source(source)) == ["z_public", "_a_protected"]

    def test_original_order_is_not_preserved(self) -> None:
        """Unlike minimize_movement, a definition already in the right group can still move."""
        source = "def z_public():\n    pass\n\ndef a_public():\n    pass\n"
        # minimize_movement leaves same-group definitions in their original order...
        assert definition_names(sort_module_source(source, sort_mode="minimize_movement")) == ["z_public", "a_public"]
        # ...alphabetical does not.
        assert definition_names(sort_module_source(source, sort_mode="alphabetical")) == ["a_public", "z_public"]

    def test_dependency_safety_still_applies(self) -> None:
        """Alphabetical mode still respects definition-time reference constraints."""
        source = "class _Base:\n    pass\n\nclass Zoo(_Base):\n    pass\n"
        assert definition_names(sort_module_source(source)) == ["_Base", "Zoo"]

    def test_default_mode_is_minimize_movement(self) -> None:
        """Omitting sort_mode keeps the original minimize-movement behavior."""
        module = cst.parse_module("def z_public():\n    pass\n\ndef a_public():\n    pass\n")
        new_module, _ = sort_module_definitions(module, ORDER, eager_annotations=True)
        assert [s.name.value for s in new_module.body if isinstance(s, cst.FunctionDef)] == [
            "z_public",
            "a_public",
        ]


class TestAlphabeticalClassSorting:
    """Tests for alphabetizing methods within a class body."""

    def test_methods_alphabetized_within_visibility(self, tmp_path: Path) -> None:
        """Methods sharing a visibility level are ordered by name."""
        source = "class Example:\n    def z(self):\n        pass\n\n    def a(self):\n        pass\n"
        target = tmp_path / "sample.py"
        target.write_text(source)

        assert sort_file(target, ORDER, sort_mode="alphabetical") is True
        result = target.read_text()
        assert result.index("def a") < result.index("def z")

    def test_property_and_setter_stay_adjacent(self, tmp_path: Path) -> None:
        """A @property/@x.setter pair shares a name, so alphabetizing keeps them together."""
        source = (
            "class Example:\n"
            "    @property\n"
            "    def z(self):\n"
            "        return self._z\n\n"
            "    def a(self):\n"
            "        pass\n\n"
            "    @z.setter\n"
            "    def z(self, value):\n"
            "        self._z = value\n"
        )
        target = tmp_path / "sample.py"
        target.write_text(source)

        assert sort_file(target, ORDER, sort_mode="alphabetical") is True
        result = target.read_text()
        # 'a' sorts before 'z', and the getter/setter pair keeps its original
        # relative order (getter before setter) since they compare equal by name.
        getter_idx = result.index("def z(self):")
        setter_idx = result.index("def z(self, value):")
        assert result.index("def a") < getter_idx < setter_idx
