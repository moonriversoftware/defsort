"""Configuration loading for undersort."""

import tomllib
from pathlib import Path
from typing import Any

from undersort import logger
from undersort.deps import parse_python_version

REQUIRED_VISIBILITIES = {"public", "protected", "private"}
OPTIONAL_VISIBILITIES = {"init", "dunder"}
VALID_VISIBILITIES = REQUIRED_VISIBILITIES | OPTIONAL_VISIBILITIES
VALID_METHOD_TYPES = {"class", "static", "instance"}
VALID_SORT_MODES = {"minimize_movement", "alphabetical"}


def load_config() -> dict[str, Any]:
    """Load configuration from pyproject.toml.

    Returns:
        Dictionary with 'order', 'method_type_order', 'exclude',
        'sort_module_level', and 'python_version' keys.
    """
    default_config: dict[str, Any] = {
        "order": ["public", "protected", "private"],
        "method_type_order": None,
        "exclude": None,
        "sort_module_level": False,
        "sort_decorated": False,
        "sort_mode": "minimize_movement",
        "python_version": None,
    }

    pyproject_path = _find_pyproject_toml()
    if not pyproject_path:
        return default_config

    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        logger.warning(f"Could not load {pyproject_path}: {e}")
        return default_config

    result: dict[str, Any] = default_config.copy()
    result["python_version"] = _project_python_version(data)

    if "tool" not in data or "undersort" not in data["tool"]:
        return result

    config = data["tool"]["undersort"]

    _load_orderings(config, result, pyproject_path)
    _load_module_level_options(config, result, pyproject_path)

    if "exclude" in config:
        exclude = config["exclude"]
        if isinstance(exclude, list):
            result["exclude"] = exclude
        else:
            logger.warning(f"Invalid exclude value in {pyproject_path}. Must be a list.")

    return result


def _load_orderings(config: dict[str, Any], result: dict[str, Any], pyproject_path: Path) -> None:
    """Read the visibility and method-type ordering options into the result.

    Args:
        config: The ``[tool.undersort]`` table
        result: The config dict to update in place
        pyproject_path: Path used in warning messages
    """
    if "order" in config:
        order = config["order"]
        problem = _order_problem(order)
        if problem:
            logger.warning(f"Invalid order in {pyproject_path}: {problem}. Using default order.")
        else:
            result["order"] = order

    if "method_type_order" in config:
        method_type_order = config["method_type_order"]
        if sorted(method_type_order) != sorted(VALID_METHOD_TYPES):
            logger.warning(f"Invalid method_type_order values in {pyproject_path}. Using default.")
        else:
            result["method_type_order"] = method_type_order


def _order_problem(order: Any) -> str | None:
    """Validate a configured visibility order.

    ``public``, ``protected`` and ``private`` must all appear, so no method can be
    silently dropped. The dunder groups are optional: leaving them out keeps magic
    methods in ``public``, which is how earlier versions behaved.

    Args:
        order: The configured value

    Returns:
        A description of the problem, or None if the order is usable
    """
    if not isinstance(order, list) or not all(isinstance(value, str) for value in order):
        return "must be a list of strings"

    unknown = [value for value in order if value not in VALID_VISIBILITIES]
    if unknown:
        return f"unknown group(s) {sorted(unknown)}; valid groups are {sorted(VALID_VISIBILITIES)}"

    if len(set(order)) != len(order):
        return "contains duplicate groups"

    missing = REQUIRED_VISIBILITIES - set(order)
    if missing:
        return f"missing required group(s) {sorted(missing)}"

    return None


def _load_module_level_options(config: dict[str, Any], result: dict[str, Any], pyproject_path: Path) -> None:
    """Read the module-level sorting options into the result.

    Args:
        config: The ``[tool.undersort]`` table
        result: The config dict to update in place
        pyproject_path: Path used in warning messages
    """
    if "sort_module_level" in config:
        sort_module_level = config["sort_module_level"]
        if isinstance(sort_module_level, bool):
            result["sort_module_level"] = sort_module_level
        else:
            logger.warning(f"Invalid sort_module_level value in {pyproject_path}. Must be a boolean.")

    if "sort_decorated" in config:
        sort_decorated = config["sort_decorated"]
        if isinstance(sort_decorated, bool):
            result["sort_decorated"] = sort_decorated
        else:
            logger.warning(f"Invalid sort_decorated value in {pyproject_path}. Must be a boolean.")

    if "sort_mode" in config:
        sort_mode = config["sort_mode"]
        if sort_mode in VALID_SORT_MODES:
            result["sort_mode"] = sort_mode
        else:
            logger.warning(
                f"Invalid sort_mode {sort_mode!r} in {pyproject_path}. "
                f"Must be one of {sorted(VALID_SORT_MODES)}. Using default."
            )

    if "python_version" in config:
        parsed = parse_python_version(str(config["python_version"]))
        if parsed is None:
            logger.warning(f"Invalid python_version value in {pyproject_path}. Ignoring.")
        else:
            result["python_version"] = parsed


def _project_python_version(data: dict[str, Any]) -> tuple[int, int] | None:
    """Infer the target Python version from the project's requires-python.

    The lower bound is used: annotation semantics must hold for the oldest
    interpreter the project claims to support.

    Args:
        data: The parsed pyproject.toml contents

    Returns:
        A (major, minor) tuple, or None if not declared
    """
    requires_python = data.get("project", {}).get("requires-python")
    if not isinstance(requires_python, str):
        return None
    return parse_python_version(requires_python)


def _find_pyproject_toml() -> Path | None:
    """Find pyproject.toml in current or parent directories.

    Returns:
        Path to pyproject.toml if found, None otherwise.
    """
    current_dir = Path.cwd()
    for directory in [current_dir, *current_dir.parents]:
        pyproject_path = directory / "pyproject.toml"
        if pyproject_path.exists():
            return pyproject_path
    return None
