"""Tests for configuration loading."""

from pathlib import Path

import pytest

from undersort.config import _find_pyproject_toml, load_config


class TestConfigLoading:
    """Tests for configuration loading from pyproject.toml."""

    def test_default_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that default config is returned when no pyproject.toml exists."""
        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {
            "order": ["public", "protected", "private"],
            "method_type_order": None,
            "exclude": None,
            "sort_module_level": False,
            "sort_decorated": False,
            "python_version": None,
        }

    def test_load_custom_order(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading custom order from pyproject.toml."""
        pyproject_content = """
[tool.undersort]
order = ["private", "protected", "public"]
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {
            "order": ["private", "protected", "public"],
            "method_type_order": None,
            "exclude": None,
            "sort_module_level": False,
            "sort_decorated": False,
            "python_version": None,
        }

    def test_invalid_order_values(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that invalid order values fall back to default."""
        pyproject_content = """
[tool.undersort]
order = ["public", "invalid", "private"]
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {
            "order": ["public", "protected", "private"],
            "method_type_order": None,
            "exclude": None,
            "sort_module_level": False,
            "sort_decorated": False,
            "python_version": None,
        }

    def test_missing_order_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that missing order key returns default."""
        pyproject_content = """
[tool.undersort]
some_other_key = "value"
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {
            "order": ["public", "protected", "private"],
            "method_type_order": None,
            "exclude": None,
            "sort_module_level": False,
            "sort_decorated": False,
            "python_version": None,
        }

    def test_missing_tool_section(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that missing tool.undersort section returns default."""
        pyproject_content = """
[project]
name = "test"
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {
            "order": ["public", "protected", "private"],
            "method_type_order": None,
            "exclude": None,
            "sort_module_level": False,
            "sort_decorated": False,
            "python_version": None,
        }

    def test_find_pyproject_in_parent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that pyproject.toml is found in parent directories."""
        # Create pyproject.toml in parent
        pyproject_content = """
[tool.undersort]
order = ["private", "public", "protected"]
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        # Change to subdirectory
        subdir = tmp_path / "subdir" / "nested"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        config = load_config()
        assert config == {
            "order": ["private", "public", "protected"],
            "method_type_order": None,
            "exclude": None,
            "sort_module_level": False,
            "sort_decorated": False,
            "python_version": None,
        }

    def test_corrupted_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that corrupted TOML file falls back to default."""
        pyproject_content = """
[tool.undersort
order = ["public"  # Invalid TOML
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {
            "order": ["public", "protected", "private"],
            "method_type_order": None,
            "exclude": None,
            "sort_module_level": False,
            "sort_decorated": False,
            "python_version": None,
        }

    def test_find_pyproject_toml_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test _find_pyproject_toml returns None when not found."""
        monkeypatch.chdir(tmp_path)
        result = _find_pyproject_toml()
        assert result is None

    def test_find_pyproject_toml_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test _find_pyproject_toml returns path when found."""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text("[project]\nname = 'test'")

        monkeypatch.chdir(tmp_path)
        result = _find_pyproject_toml()
        assert result == pyproject_path

    def test_load_exclude_patterns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading exclude patterns from pyproject.toml."""
        pyproject_content = """
[tool.undersort]
order = ["public", "protected", "private"]
exclude = ["tests/*", "migrations/*.py"]
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {
            "order": ["public", "protected", "private"],
            "method_type_order": None,
            "exclude": ["tests/*", "migrations/*.py"],
            "sort_module_level": False,
            "sort_decorated": False,
            "python_version": None,
        }

    def test_invalid_exclude_type(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that invalid exclude type falls back to None."""
        pyproject_content = """
[tool.undersort]
order = ["public", "protected", "private"]
exclude = "invalid"
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert config == {
            "order": ["public", "protected", "private"],
            "method_type_order": None,
            "exclude": None,
            "sort_module_level": False,
            "sort_decorated": False,
            "python_version": None,
        }

    def test_sort_module_level_enabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that sort_module_level is read from pyproject.toml."""
        pyproject_content = """
[tool.undersort]
sort_module_level = true
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        assert load_config()["sort_module_level"] is True

    def test_invalid_sort_module_level(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a non-boolean sort_module_level falls back to the default."""
        pyproject_content = """
[tool.undersort]
sort_module_level = "yes"
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        assert load_config()["sort_module_level"] is False

    def test_python_version_from_requires_python(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that the target version is inferred from the project's requires-python."""
        pyproject_content = """
[project]
name = "test"
requires-python = ">=3.10,<4.0"
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        assert load_config()["python_version"] == (3, 10)

    def test_explicit_python_version_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that an explicit python_version overrides requires-python."""
        pyproject_content = """
[project]
name = "test"
requires-python = ">=3.10"

[tool.undersort]
python_version = "3.14"
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        assert load_config()["python_version"] == (3, 14)

    def test_invalid_python_version_ignored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that an unparseable python_version is ignored."""
        pyproject_content = """
[tool.undersort]
python_version = "nonsense"
"""
        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(pyproject_content)

        monkeypatch.chdir(tmp_path)
        assert load_config()["python_version"] is None
