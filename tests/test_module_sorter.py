"""Tests for module-level definition sorting."""

from pathlib import Path

import libcst as cst
import pytest

from defsort.deps import annotations_are_eager, has_future_annotations, parse_python_version
from defsort.sorter import sort_file, sort_module_definitions

ORDER = ["public", "protected", "private"]


def sort_source(source: str, eager_annotations: bool = True, order: list[str] | None = None) -> str:
    """Sort module-level definitions in a source snippet.

    Args:
        source: The source code
        eager_annotations: Whether annotations are evaluated at definition time
        order: Visibility ordering, defaults to public/protected/private

    Returns:
        The sorted source code
    """
    module = cst.parse_module(source)
    new_module, _ = sort_module_definitions(module, order or ORDER, eager_annotations)
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


class TestBasicModuleSorting:
    """Tests for ordering module-level definitions by visibility."""

    def test_functions_sorted_by_visibility(self) -> None:
        """Module-level functions are grouped public, protected, private."""
        source = "def _helper():\n    pass\n\ndef public_a():\n    pass\n\ndef __private():\n    pass\n"
        assert definition_names(sort_source(source)) == ["public_a", "_helper", "__private"]

    def test_classes_and_functions_sorted_together(self) -> None:
        """Classes and functions share one ordering stream."""
        source = "class _Helper:\n    pass\n\ndef public_fn():\n    pass\n\nclass Public:\n    pass\n"
        assert definition_names(sort_source(source)) == ["public_fn", "Public", "_Helper"]

    def test_dunder_names_are_public(self) -> None:
        """Magic-style module names follow the public rule."""
        source = "def _helper():\n    pass\n\ndef __getattr__(name):\n    pass\n"
        assert definition_names(sort_source(source)) == ["__getattr__", "_helper"]

    def test_custom_order(self) -> None:
        """A custom visibility order is honoured."""
        source = "def public_a():\n    pass\n\ndef _helper():\n    pass\n"
        result = sort_source(source, order=["private", "protected", "public"])
        assert definition_names(result) == ["_helper", "public_a"]

    def test_already_sorted_is_unchanged(self) -> None:
        """A sorted module is reported as unmodified and byte-identical."""
        source = "def public_a():\n    pass\n\ndef _helper():\n    pass\n"
        module = cst.parse_module(source)
        new_module, modified = sort_module_definitions(module, ORDER, True)
        assert modified is False
        assert new_module.code == source

    def test_blank_lines_preserved(self) -> None:
        """Blank-line spacing stays with the slot, not the moved definition."""
        source = "def _helper():\n    pass\n\n\ndef public_a():\n    pass\n"
        assert sort_source(source) == "def public_a():\n    pass\n\n\ndef _helper():\n    pass\n"

    def test_leading_comments_follow_their_definition(self) -> None:
        """A comment above a definition moves with it."""
        source = "import os\n\n# about helper\ndef _helper():\n    pass\n\n# about public\ndef public_a():\n    pass\n"
        result = sort_source(source)
        assert result.index("# about public") < result.index("def public_a")
        assert result.index("# about helper") < result.index("def _helper")
        assert result.index("def public_a") < result.index("# about helper")

    def test_first_definition_pinned_when_header_comment_touches_it(self) -> None:
        """A comment in the module header would be stranded, so the first definition stays."""
        source = "# about helper\ndef _helper():\n    pass\n\ndef public_a():\n    pass\n"
        assert definition_names(sort_source(source)) == ["_helper", "public_a"]

    def test_first_definition_moves_when_header_comment_is_detached(self) -> None:
        """A module banner separated by a blank line does not pin the first definition."""
        source = "# module banner\n\ndef _helper():\n    pass\n\ndef public_a():\n    pass\n"
        result = sort_source(source)
        assert definition_names(result) == ["public_a", "_helper"]
        assert result.startswith("# module banner\n")


class TestDependencySafety:
    """Tests that reordering never breaks definition-time references."""

    def test_base_class_stays_first(self) -> None:
        """A protected base class is not moved below its subclass."""
        source = "class _Base:\n    pass\n\nclass Child(_Base):\n    pass\n"
        assert definition_names(sort_source(source)) == ["_Base", "Child"]

    def test_metaclass_keyword_stays_first(self) -> None:
        """A metaclass referenced by keyword constrains ordering."""
        source = "class _Meta(type):\n    pass\n\nclass Public(metaclass=_Meta):\n    pass\n"
        assert definition_names(sort_source(source)) == ["_Meta", "Public"]

    def test_decorator_stays_first(self) -> None:
        """A protected decorator is not moved below the function it decorates."""
        source = "def _register(fn):\n    return fn\n\n@_register\ndef public_thing():\n    pass\n"
        assert definition_names(sort_source(source)) == ["_register", "public_thing"]

    def test_dotted_decorator_stays_first(self) -> None:
        """An attribute-style decorator constrains ordering via its base name."""
        source = "class _Registry:\n    pass\n\n@_Registry.register\ndef public_thing():\n    pass\n"
        assert definition_names(sort_source(source)) == ["_Registry", "public_thing"]

    def test_default_value_stays_first(self) -> None:
        """A default argument value is evaluated at definition time."""
        source = "def _default():\n    return 1\n\ndef public_fn(x=_default()):\n    return x\n"
        assert definition_names(sort_source(source)) == ["_default", "public_fn"]

    def test_class_body_reference_stays_first(self) -> None:
        """A class body executes eagerly, so its references constrain ordering."""
        source = "def _make():\n    return 1\n\nclass Public:\n    value = _make()\n"
        assert definition_names(sort_source(source)) == ["_make", "Public"]

    def test_function_body_reference_is_not_a_constraint(self) -> None:
        """References inside a function body resolve at call time and can be reordered."""
        source = "def _helper():\n    return 1\n\ndef public_fn():\n    return _helper()\n"
        assert definition_names(sort_source(source)) == ["public_fn", "_helper"]

    def test_method_body_reference_is_not_a_constraint(self) -> None:
        """A method body is lazy even though the surrounding class body is eager."""
        source = "def _helper():\n    return 1\n\nclass Public:\n    def run(self):\n        return _helper()\n"
        assert definition_names(sort_source(source)) == ["Public", "_helper"]

    def test_transitive_constraint(self) -> None:
        """Chained definition-time dependencies are all respected."""
        source = "class _A:\n    pass\n\nclass _B(_A):\n    pass\n\nclass Public(_B):\n    pass\n"
        assert definition_names(sort_source(source)) == ["_A", "_B", "Public"]

    def test_unconstrained_definitions_still_move(self) -> None:
        """A constraint on one definition does not freeze unrelated ones."""
        source = (
            "class _Base:\n    pass\n\n"
            "class Child(_Base):\n    pass\n\n"
            "def _free():\n    pass\n\n"
            "def public_fn():\n    pass\n"
        )
        assert definition_names(sort_source(source)) == ["public_fn", "_Base", "Child", "_free"]


class TestAnnotationHandling:
    """Tests for eager versus lazy annotation evaluation."""

    def test_eager_annotation_constrains_ordering(self) -> None:
        """With eager annotations, an annotated type must stay above its user."""
        source = "class _Model:\n    pass\n\ndef public_fn(x: _Model) -> _Model:\n    return x\n"
        assert definition_names(sort_source(source, eager_annotations=True)) == ["_Model", "public_fn"]

    def test_lazy_annotation_does_not_constrain_ordering(self) -> None:
        """With lazy annotations, the annotated type may move below its user."""
        source = "class _Model:\n    pass\n\ndef public_fn(x: _Model) -> _Model:\n    return x\n"
        assert definition_names(sort_source(source, eager_annotations=False)) == ["public_fn", "_Model"]

    def test_eager_class_level_annotation_constrains_ordering(self) -> None:
        """An annotated class attribute is evaluated when the class body runs."""
        source = "class _Model:\n    pass\n\nclass Public:\n    field: _Model\n"
        assert definition_names(sort_source(source, eager_annotations=True)) == ["_Model", "Public"]

    def test_future_import_detected(self) -> None:
        """``from __future__ import annotations`` is recognised."""
        module = cst.parse_module("from __future__ import annotations\n\nx = 1\n")
        assert has_future_annotations(module) is True
        assert annotations_are_eager(module, (3, 11)) is False

    def test_no_future_import(self) -> None:
        """A module without the future import has eager annotations on old versions."""
        module = cst.parse_module("import os\n\nx = 1\n")
        assert has_future_annotations(module) is False
        assert annotations_are_eager(module, (3, 11)) is True

    def test_other_future_import_does_not_count(self) -> None:
        """An unrelated ``__future__`` import does not make annotations lazy."""
        module = cst.parse_module("from __future__ import division\n")
        assert has_future_annotations(module) is False

    def test_python_314_annotations_are_lazy(self) -> None:
        """PEP 649 makes annotations lazy from 3.14 onwards."""
        module = cst.parse_module("import os\n")
        assert annotations_are_eager(module, (3, 14)) is False
        assert annotations_are_eager(module, (3, 13)) is True

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (">=3.9", (3, 9)),
            (">=3.10,<4.0", (3, 10)),
            ("~=3.12", (3, 12)),
            ("3.11", (3, 11)),
            ("3.12.4", (3, 12)),
            ("py313", (3, 13)),
            ("nonsense", None),
        ],
    )
    def test_parse_python_version(self, value: str, expected: tuple[int, int] | None) -> None:
        """Version strings and requirement specifiers are parsed to (major, minor)."""
        assert parse_python_version(value) == expected


class TestBarriersAndPins:
    """Tests for statements and directives that block reordering."""

    def test_non_definition_statement_is_a_barrier(self) -> None:
        """Definitions never move across a non-definition top-level statement."""
        source = "def _a():\n    pass\n\nX = 1\n\ndef public_b():\n    pass\n"
        assert definition_names(sort_source(source)) == ["_a", "public_b"]

    def test_sorting_happens_within_each_run(self) -> None:
        """Each run between barriers is sorted independently."""
        source = (
            "def _a():\n    pass\n\ndef public_a():\n    pass\n\n"
            "X = 1\n\n"
            "def _b():\n    pass\n\ndef public_b():\n    pass\n"
        )
        assert definition_names(sort_source(source)) == ["public_a", "_a", "public_b", "_b"]

    def test_nosort_definition_stays_put(self) -> None:
        """A definition marked ``# nosort`` keeps its position."""
        source = "def public_a():\n    pass\n\ndef _keep():  # nosort\n    pass\n\ndef public_b():\n    pass\n"
        assert definition_names(sort_source(source)) == ["public_a", "_keep", "public_b"]

    def test_redefined_names_stay_put(self) -> None:
        """Overloads and other redefinitions of one name are never reordered."""
        source = (
            "@overload\ndef public_f(x: int) -> int: ...\n\n"
            "def _helper():\n    pass\n\n"
            "@overload\ndef public_f(x: str) -> str: ...\n"
        )
        assert definition_names(sort_source(source)) == ["public_f", "_helper", "public_f"]

    def test_imports_are_barriers(self) -> None:
        """Definitions stay below the imports above them."""
        source = "import os\n\ndef _helper():\n    pass\n\ndef public_a():\n    pass\n"
        result = sort_source(source)
        assert result.index("import os") < result.index("def public_a")


class TestSortFileIntegration:
    """Tests for the module-level mode through sort_file."""

    def test_disabled_by_default(self, tmp_path: Path) -> None:
        """Module-level definitions are untouched unless the mode is enabled."""
        source = "def _helper():\n    pass\n\n\ndef public_a():\n    pass\n"
        target = tmp_path / "sample.py"
        target.write_text(source)

        assert sort_file(target, ORDER) is False
        assert target.read_text() == source

    def test_enabled_sorts_module_level(self, tmp_path: Path) -> None:
        """With the mode enabled, module-level definitions are reordered."""
        source = "def _helper():\n    pass\n\n\ndef public_a():\n    pass\n"
        target = tmp_path / "sample.py"
        target.write_text(source)

        assert sort_file(target, ORDER, sort_module_level=True) is True
        assert definition_names(target.read_text()) == ["public_a", "_helper"]

    def test_check_only_does_not_write(self, tmp_path: Path) -> None:
        """Check mode reports the need to sort without touching the file."""
        source = "def _helper():\n    pass\n\n\ndef public_a():\n    pass\n"
        target = tmp_path / "sample.py"
        target.write_text(source)

        assert sort_file(target, ORDER, sort_module_level=True, check_only=True) is True
        assert target.read_text() == source

    def test_file_level_nosort_respected(self, tmp_path: Path) -> None:
        """A file-level nosort directive disables module-level sorting too."""
        source = "# nosort: file\ndef _helper():\n    pass\n\n\ndef public_a():\n    pass\n"
        target = tmp_path / "sample.py"
        target.write_text(source)

        assert sort_file(target, ORDER, sort_module_level=True) is False
        assert target.read_text() == source

    def test_python_version_controls_annotation_handling(self, tmp_path: Path) -> None:
        """A 3.14+ target lets annotated types move below their users."""
        source = "class _Model:\n    pass\n\n\ndef public_fn(x: _Model) -> _Model:\n    return x\n"

        eager = tmp_path / "eager.py"
        eager.write_text(source)
        assert sort_file(eager, ORDER, sort_module_level=True, python_version=(3, 11)) is False

        lazy = tmp_path / "lazy.py"
        lazy.write_text(source)
        assert sort_file(lazy, ORDER, sort_module_level=True, python_version=(3, 14)) is True
        assert definition_names(lazy.read_text()) == ["public_fn", "_Model"]

    def test_methods_and_module_level_sorted_together(self, tmp_path: Path) -> None:
        """Class methods and module-level definitions are sorted in one pass."""
        source = (
            "def _helper():\n    pass\n\n\n"
            "class Public:\n    def _protected(self):\n        pass\n\n"
            "    def public_method(self):\n        pass\n"
        )
        target = tmp_path / "sample.py"
        target.write_text(source)

        assert sort_file(target, ORDER, sort_module_level=True) is True
        result = target.read_text()
        assert definition_names(result) == ["Public", "_helper"]
        assert result.index("def public_method") < result.index("def _protected")


class TestSideEffectSafety:
    """Tests for the conservative handling of import-time side effects."""

    def test_decorated_definitions_pinned_by_default(self) -> None:
        """Decorated definitions do not move, since decorators can run at import time."""
        source = "@register\ndef _b():\n    pass\n\n@register\ndef public_a():\n    pass\n"
        assert definition_names(sort_source(source)) == ["_b", "public_a"]

    def test_decorated_definitions_move_when_opted_in(self) -> None:
        """sort_decorated allows decorated definitions to be reordered."""
        source = "@register\ndef _b():\n    pass\n\n@register\ndef public_a():\n    pass\n"
        module = cst.parse_module(source)
        new_module, modified = sort_module_definitions(module, ORDER, True, sort_decorated=True)
        assert modified is True
        assert definition_names(new_module.code) == ["public_a", "_b"]

    def test_decorated_definition_anchors_its_neighbours(self) -> None:
        """Nothing is reordered across a pinned decorated definition."""
        source = "def _a():\n    pass\n\n@register\ndef _dec():\n    pass\n\ndef public_b():\n    pass\n"
        assert definition_names(sort_source(source)) == ["_a", "_dec", "public_b"]


class TestFileFidelity:
    """Tests that rewriting a file preserves its byte-level characteristics."""

    def test_crlf_line_endings_preserved(self, tmp_path: Path) -> None:
        """A CRLF file is not silently converted to LF."""
        target = tmp_path / "crlf.py"
        target.write_bytes(b"def _helper():\r\n    pass\r\n\r\n\r\ndef public_a():\r\n    pass\r\n")

        assert sort_file(target, ORDER, sort_module_level=True) is True
        data = target.read_bytes()
        assert data.count(b"\r\n") == data.count(b"\n")

    def test_bom_preserved(self, tmp_path: Path) -> None:
        """A UTF-8 BOM survives the rewrite."""
        target = tmp_path / "bom.py"
        target.write_bytes(b"\xef\xbb\xbfdef _helper():\n    pass\n\n\ndef public_a():\n    pass\n")

        assert sort_file(target, ORDER, sort_module_level=True) is True
        assert target.read_bytes().startswith(b"\xef\xbb\xbf")

    def test_declared_encoding_respected(self, tmp_path: Path) -> None:
        """A PEP 263 coding declaration is honoured on both read and write."""
        target = tmp_path / "latin.py"
        body = "def _helper():\n    pass\n\n\ndef public_a():\n    pass\n\n\nS = 'é'\n"
        target.write_bytes(b"# -*- coding: latin-1 -*-\n\n" + body.encode("latin-1"))

        assert sort_file(target, ORDER, sort_module_level=True) is True
        text = target.read_bytes().decode("latin-1")
        assert "S = 'é'" in text
        assert definition_names(text) == ["public_a", "_helper"]
