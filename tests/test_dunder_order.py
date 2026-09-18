"""Tests for splitting dunder methods out of the public group (issue #1)."""

from pathlib import Path

import libcst as cst
import pytest

from defsort.config import load_config
from defsort.sorter import MethodSorter, get_method_visibility, is_dunder, sort_module_definitions

FULL = ["init", "dunder", "public", "protected", "private"]
LEGACY = ["public", "protected", "private"]
TYPE_ORDER = ["static", "class", "instance"]


def method_names(source: str) -> list[str]:
    """List method names of the first class, in order.

    Args:
        source: The source code

    Returns:
        The method names
    """
    module = cst.parse_module(source)
    class_def = next(s for s in module.body if isinstance(s, cst.ClassDef))
    return [item.name.value for item in class_def.body.body if isinstance(item, cst.FunctionDef)]


def sort_class(source: str, order: list[str], method_type_order: list[str] | None = None) -> str:
    """Sort methods of a class snippet with the given ordering.

    Args:
        source: The source code
        order: Visibility ordering
        method_type_order: Optional method type ordering

    Returns:
        The sorted source
    """
    module = cst.parse_module(source)
    return module.visit(MethodSorter(order, method_type_order)).code


SAMPLE = """class C:
    def _helper(self): ...

    @classmethod
    def default(cls): ...

    def __init__(self) -> None: ...

    def public_a(self): ...

    def __str__(self) -> str: ...

    def __private(self): ...
"""


class TestVisibilityClassification:
    """Tests for the order-aware visibility classifier."""

    def test_dunder_detection(self) -> None:
        """Only names wrapped in double underscores are dunders."""
        assert is_dunder("__init__") is True
        assert is_dunder("__str__") is True
        assert is_dunder("__private") is False
        assert is_dunder("_protected") is False
        assert is_dunder("public") is False

    def test_dunders_are_public_without_configuration(self) -> None:
        """Legacy behaviour: magic methods count as public."""
        assert get_method_visibility("__init__") == "public"
        assert get_method_visibility("__str__", LEGACY) == "public"

    def test_dunder_group_captures_magic_methods(self) -> None:
        """With a dunder group, magic methods leave the public group."""
        order = ["dunder", "public", "protected", "private"]
        assert get_method_visibility("__str__", order) == "dunder"
        assert get_method_visibility("__init__", order) == "dunder"

    def test_init_group_captures_creational_dunders(self) -> None:
        """Creational dunders form their own group when requested."""
        assert get_method_visibility("__init__", FULL) == "init"
        assert get_method_visibility("__new__", FULL) == "init"
        assert get_method_visibility("__init_subclass__", FULL) == "init"
        assert get_method_visibility("__post_init__", FULL) == "init"
        assert get_method_visibility("__str__", FULL) == "dunder"

    def test_init_group_without_dunder_group(self) -> None:
        """Non-creational dunders fall back to public when no dunder group exists."""
        order = ["init", "public", "protected", "private"]
        assert get_method_visibility("__init__", order) == "init"
        assert get_method_visibility("__str__", order) == "public"

    def test_non_dunder_underscores_unaffected(self) -> None:
        """Name-mangled and protected names keep their existing groups."""
        assert get_method_visibility("__private", FULL) == "private"
        assert get_method_visibility("_protected", FULL) == "protected"
        assert get_method_visibility("public", FULL) == "public"


class TestIssueScenarios:
    """The two cases reported in issue #1."""

    def test_init_no_longer_trails_a_classmethod(self) -> None:
        """__init__ can be pulled ahead of a public classmethod."""
        source = "class C:\n    @classmethod\n    def default(cls): ...\n\n    def __init__(self) -> None: ...\n"
        assert method_names(sort_class(source, FULL, TYPE_ORDER)) == ["__init__", "default"]

    def test_dunders_group_together(self) -> None:
        """__init__ and __str__ end up adjacent instead of split by a public method."""
        source = (
            "class C:\n    def __init__(self) -> None: ...\n\n"
            "    def random_public(self): ...\n\n"
            "    def __str__(self) -> str: ...\n"
        )
        assert method_names(sort_class(source, FULL, TYPE_ORDER)) == ["__init__", "__str__", "random_public"]

    def test_legacy_order_is_unchanged(self) -> None:
        """An order without dunder groups keeps magic methods in the public group."""
        assert method_names(sort_class(SAMPLE, LEGACY, TYPE_ORDER)) == [
            "default",
            "__init__",
            "public_a",
            "__str__",
            "_helper",
            "__private",
        ]

    def test_full_order_groups_everything(self) -> None:
        """Creational, generic dunder, public, protected and private all separate."""
        assert method_names(sort_class(SAMPLE, FULL, TYPE_ORDER)) == [
            "__init__",
            "__str__",
            "default",
            "public_a",
            "_helper",
            "__private",
        ]

    def test_dunders_can_be_placed_last(self) -> None:
        """The groups are positional, so dunders can also go at the end."""
        order = ["public", "protected", "private", "init", "dunder"]
        assert method_names(sort_class(SAMPLE, order, TYPE_ORDER))[-2:] == ["__init__", "__str__"]

    def test_blank_lines_stay_sane(self) -> None:
        """Moving a dunder to the front does not collapse the spacing."""
        source = "class C:\n    @classmethod\n    def default(cls): ...\n\n    def __init__(self) -> None: ...\n"
        result = sort_class(source, FULL, TYPE_ORDER)
        assert (
            result == "class C:\n    def __init__(self) -> None: ...\n\n    @classmethod\n    def default(cls): ...\n"
        )


class TestOrderValidation:
    """Tests for validating the extended order option."""

    @pytest.mark.parametrize(
        "order",
        [
            ["init", "dunder", "public", "protected", "private"],
            ["dunder", "public", "protected", "private"],
            ["public", "protected", "private"],
            ["private", "protected", "public"],
        ],
    )
    def test_valid_orders_accepted(self, order: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Orders containing all required groups are accepted."""
        (tmp_path / "pyproject.toml").write_text(f"[tool.defsort]\norder = {order!r}\n".replace("'", '"'))
        monkeypatch.chdir(tmp_path)
        assert load_config()["order"] == order

    @pytest.mark.parametrize(
        "order",
        [
            ["init", "dunder", "public"],
            ["public", "protected", "private", "bogus"],
            ["public", "public", "protected", "private"],
            "notalist",
        ],
    )
    def test_invalid_orders_fall_back(self, order: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Incomplete, unknown, duplicated or malformed orders fall back to the default."""
        rendered = repr(order).replace("'", '"')
        (tmp_path / "pyproject.toml").write_text(f"[tool.defsort]\norder = {rendered}\n")
        monkeypatch.chdir(tmp_path)
        assert load_config()["order"] == ["public", "protected", "private"]


class TestModuleLevelDunders:
    """Dunder grouping also applies to module-level definitions."""

    def test_module_dunder_grouped(self) -> None:
        """A module-level __getattr__ follows the configured dunder group."""
        source = "def _helper():\n    pass\n\n\ndef __getattr__(name):\n    pass\n"
        module = cst.parse_module(source)
        new_module, modified = sort_module_definitions(module, FULL, True)
        assert modified is True
        assert new_module.code.index("__getattr__") < new_module.code.index("_helper")
