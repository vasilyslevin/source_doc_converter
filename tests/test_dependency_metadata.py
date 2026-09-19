import tomllib
from pathlib import Path


def test_runtime_dependencies_include_pypdf() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = project.get("dependencies", [])

    assert any(str(item).startswith("pypdf") for item in dependencies)
