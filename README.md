# undersort

A Python tool that automatically sorts class methods by visibility (public, protected, private) and type (class, static, instance).

## Features

- Automatically reorders class methods based on visibility and method type
- Two-level sorting: primary by visibility, secondary by method type
- Optional module-level mode that sorts top-level functions and classes, with
  dependency analysis so decorators, base classes, and annotations keep working
- Fully configurable ordering via `pyproject.toml`
- Pre-commit hook integration
- Colored output for better readability
- Check mode for CI/CD validation
- Diff mode to preview changes

## Installation

```bash
# Using uv (recommended)
uv add undersort

# Using pip
pip install undersort

# For development
git clone https://github.com/kivicode/undersort
cd undersort
uv sync
```

## Configuration

Configure the method ordering in your `pyproject.toml`:

```toml
[tool.undersort]
# Method visibility ordering (primary sort)
# Required groups: "public", "protected", "private"
# Optional groups: "init" (creational dunders), "dunder" (all other magic methods)
# Omit the optional groups to keep magic methods inside "public" (the default).
order = ["public", "protected", "private"]

# Method type ordering within each visibility level (secondary sort, optional)
# Options: "class" (classmethod), "static" (staticmethod), "instance" (regular methods)
# Default: ["instance", "class", "static"]
method_type_order = ["instance", "class", "static"]

# Exclude files/directories matching these patterns (optional)
# Patterns support glob syntax (e.g., "tests/*", "migrations/*.py", "**/generated/*")
# exclude = ["tests/*", "migrations/*.py"]

# Also sort module-level functions and classes (optional, default: false)
# sort_module_level = true

# Allow decorated module-level definitions to move (optional, default: false)
# Leave off unless your decorators have no order-dependent import-time side effects
# sort_decorated = true

# How to order definitions within a group (optional, default: "minimize_movement")
# "minimize_movement" preserves as much of the original order as possible.
# "alphabetical" ignores original order and sorts purely by name within each group.
# sort_mode = "alphabetical"

# Target Python version, used to decide whether annotations are evaluated eagerly
# (optional; inferred from [project] requires-python when not set)
# python_version = "3.12"
```

### Method Visibility Rules

- **Public methods**: No underscore prefix (e.g., `def method()`) or magic methods (e.g., `__init__`, `__str__`)
- **Protected methods**: Single underscore prefix (e.g., `def _method()`)
- **Private methods**: Double underscore prefix, not magic (e.g., `def __method()`)

#### Separating dunder methods

By default magic methods count as **public**, which leaves `__init__` mixed in with
ordinary public methods. Add either of the two optional groups to `order` to pull
them out:

- **`init`** — creational dunders: `__new__`, `__init__`, `__init_subclass__`, `__post_init__`
- **`dunder`** — every other magic method: `__str__`, `__get__`, `__eq__`, ...

```toml
[tool.undersort]
order = ["init", "dunder", "public", "protected", "private"]
method_type_order = ["static", "class", "instance"]
```

```python
# before                              # after
class C:                              class C:
    @classmethod                          def __init__(self) -> None: ...
    def default(cls): ...
                                          def __str__(self) -> str: ...
    def __init__(self) -> None: ...
                                          @classmethod
    def random_public(self): ...          def default(cls): ...

    def __str__(self) -> str: ...         def random_public(self): ...
```

The groups are positional, so `order = ["public", "protected", "private", "init", "dunder"]`
puts the magic methods last instead.

Notes:

- `public`, `protected` and `private` must always be present, so no method can be
  silently dropped. `init` and `dunder` are optional.
- Using `init` without `dunder` leaves non-creational magic methods in `public`.
- Name-mangled methods (`__method`, no trailing underscores) remain **private** —
  they are not dunders.
- An existing `order` that does not mention the new groups behaves exactly as before.

### Method Type Rules

- **Class methods**: Decorated with `@classmethod`
- **Static methods**: Decorated with `@staticmethod`
- **Instance methods**: Regular methods (no special decorator)

### Sorting Behavior

Methods are sorted in two levels:

1. **Primary**: By visibility (public → protected → private)
2. **Secondary**: Within each visibility level, by method type (instance → class → static by default)

Within each (visibility, method type) group, `sort_mode` decides how members of that
group are ordered relative to each other:

- **`minimize_movement`** (default): preserves the original order as much as possible.
  - Methods that need to move DOWN (to a later section) are placed at the **beginning** of their target section
  - Methods that need to move UP (to an earlier section) are placed at the **end** of their target section
  - Methods already in the correct section maintain their relative order
- **`alphabetical`**: ignores original position entirely and orders members of each
  group purely by name. A `@property`/`@x.setter` pair (or any two definitions
  sharing a name) still stays adjacent, in its original relative order, since they
  compare equal under the sort key.

```toml
[tool.undersort]
sort_mode = "alphabetical"
```

```bash
undersort --sort-mode alphabetical src/
```

Example order with default configuration (`minimize_movement`):

1. Public instance methods
2. Public class methods
3. Public static methods
4. Protected instance methods
5. Protected class methods
6. Protected static methods
7. Private instance methods
8. Private class methods
9. Private static methods

## Module-Level Sorting (optional)

By default undersort only reorders methods inside classes. Enable `sort_module_level`
to apply the same visibility ordering to top-level functions and classes:

```toml
[tool.undersort]
sort_module_level = true
```

Or from the command line: `undersort --sort-module-level src/` (use
`--no-sort-module-level` to override the config file for one run).

Classes and functions are ordered in a single stream by the same naming rules
(`public` → `protected` → `private`).

### Safety Rules

Unlike methods in a class body, module-level definitions execute in order, so
reordering them can break a module. undersort only moves a definition when it is
provably safe:

**Non-definition statements are barriers.** Definitions are only reordered within
runs of consecutive `def`/`class` statements. An import, assignment, or `if` block
between them splits the file into independent runs, so nothing moves across it:

```python
def _helper(): ...
def public_a(): ...    # these two are sorted together

CONSTANT = compute()   # barrier -- nothing crosses this line

def _other(): ...
def public_b(): ...    # these two are sorted together
```

**Definition-time references are respected.** A definition never moves above
something it needs when it is defined. That includes decorators, base classes and
`metaclass=` keywords, default argument values, and class bodies (which run
eagerly, though method bodies inside them do not):

```python
class _Base: ...

class Public(_Base):   # stays below _Base despite being public
    ...
```

References made inside a function or method body impose no constraint, since they
resolve when the function is called rather than when it is defined.

**Annotations are handled according to the effective evaluation semantics.**
Annotations are eagerly evaluated -- and therefore constrain ordering -- unless
either of the following applies, in which case annotated types are free to move:

- the module starts with `from __future__ import annotations` (PEP 563)
- the target Python version is 3.14 or newer, where annotations are lazy by
  default (PEP 649)

The target version comes from `python_version`, or the project's
`requires-python` lower bound, or the running interpreter, in that order.

**Redefined names never move.** If a name is defined more than once at the top
level (`@overload` blocks, `@singledispatch` registrations, conditional
redefinitions), all of its definitions stay put.

**Decorated definitions are pinned by default.** A decorator runs at import time
and can have side effects whose *order* matters — `@app.route`, `@cli.command`,
`@register` and friends append to a registry as the module loads. No static
analysis can tell a registering decorator from a pure one, so decorated
definitions keep their position unless you opt in:

```toml
[tool.undersort]
sort_decorated = true    # only if you know your decorators are order-independent
```

**`# nosort` still applies**, both file-level and on individual definitions.
Note that at module level a pinned definition acts as a hard anchor: nothing is
reordered across it. This is stricter than the class-method behaviour, because
top-level statements execute in order.

### Known Limitation

undersort guarantees that reordering never breaks *name resolution* — nothing
moves above a name it needs at definition time. It cannot fully guarantee
*side-effect order*. Pinning decorated definitions covers the common registry
pattern, but two cases remain outside static reach:

- classes whose creation has side effects through a base class defined in another
  module (`__init_subclass__` hooks, registering metaclasses)
- any definition whose mere position is load-bearing for reasons not visible in
  the file

If your module has import-time ordering semantics like these, mark the affected
definitions with `# nosort`, or leave `sort_module_level` off for that file.

### Skipping Sorting with `# nosort`

You can prevent sorting at different levels using `# nosort` comments (case-insensitive):

**File-level**: Skip entire file

```python
# nosort: file
class Example:
    def _protected(self):
        pass
    def public(self):
        pass  # File won't be sorted
```

**Class-level**: Skip specific class

```python
class Example:  # nosort
    def _protected(self):
        pass
    def public(self):
        pass  # This class won't be sorted

class Other:
    def _protected(self):
        pass
    def public(self):
        pass  # This class WILL be sorted
```

**Method-level**: Keep method in its current position

```python
class Example:
    def public_a(self):
        pass

    def _protected(self):  # nosort
        pass  # Stays here, between public methods

    def public_b(self):
        pass  # Will move up, but _protected stays in place
```

## Usage

### Command Line

```bash
# Sort a single file
undersort example.py

# Sort multiple files
undersort file1.py file2.py file3.py

# Sort all Python files in a directory (recursive by default)
undersort src/

# Sort all Python files in current directory and subdirectories
undersort .

# Non-recursive directory sorting (only files in the directory, not subdirectories)
undersort src/ --no-recursive

# Wildcards work too (expanded by shell)
undersort *.py
undersort src/**/*.py

# Check if files need sorting (useful for CI)
undersort --check example.py
undersort --check src/

# Show diff of changes
undersort --diff example.py

# Combine flags
undersort --check --diff src/

# Exclude specific files or directories
undersort --exclude "tests/*" --exclude "migrations/*.py" src/

# Multiple exclude patterns (can be combined with config file patterns)
undersort --exclude "test_*.py" --exclude "*/legacy/*" .

# Also sort module-level functions and classes
undersort --sort-module-level src/

# Override the config file for a single run
undersort --no-sort-module-level src/

# Tell undersort which Python version to assume for annotation semantics
undersort --sort-module-level --python-version 3.14 src/

# Also reorder decorated definitions (off by default, see Known Limitation)
undersort --sort-module-level --sort-decorated src/

# Alphabetize within each group instead of minimizing movement (applies to
# both class methods and, when enabled, module-level definitions)
undersort --sort-mode alphabetical src/
```

**Note**: By default, undersort excludes all dot-prefixed directories (e.g., `.venv`, `.git`, `.pytest_cache`) and common build directories (`venv`, `__pycache__`, `node_modules`) when scanning directories recursively. You can add custom exclusions via CLI flags or the config file.

### Pre-commit Integration

Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: undersort
        name: undersort
        entry: undersort
        language: python
        types: [python]
        additional_dependencies: ["undersort"]
```

Then install the hook:

```bash
pip install pre-commit
pre-commit install
```

## Example

### Before

```python
class Example:
    def _protected_instance(self):
        pass

    @staticmethod
    def public_static():
        pass

    def __init__(self):
        pass

    @classmethod
    def _protected_class(cls):
        pass

    def public_instance(self):
        pass

    def __private_method(self):
        pass

    @classmethod
    def public_class(cls):
        pass
```

### After (with default config)

```python
class Example:
    def __init__(self):
        pass

    def public_instance(self):
        pass

    @classmethod
    def public_class(cls):
        pass

    @staticmethod
    def public_static():
        pass

    def _protected_instance(self):
        pass

    @classmethod
    def _protected_class(cls):
        pass

    def __private_method(self):
        pass
```

The methods are now organized by:

1. **Visibility**: public (including `__init__`) → protected → private
2. **Type** (within each visibility): instance → class → static

## Development

```bash
# Install dependencies
uv sync

# Run on example file
uv run undersort example.py

# Test with check mode
uv run undersort --check example.py

# View diff
uv run undersort --diff example.py
```

## License

MIT
