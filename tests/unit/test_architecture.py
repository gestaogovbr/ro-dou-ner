import ast
from pathlib import Path


def test_dependency_direction_and_sdk_isolation():
    root = Path(__file__).parents[2] / "src/ro_dou_ner"
    for layer in ("domain", "application"):
        for path in (root / layer).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                for module in modules:
                    assert not module.startswith(
                        (
                            "ro_dou_ner.adapters",
                            "ro_dou_ner.bootstrap",
                            "airflow",
                            "gliner",
                            "psycopg",
                            "opensearchpy",
                            "fastapi",
                            "torch",
                        )
                    ), f"{path} imports {module}"
                    if layer == "domain":
                        assert not module.startswith("ro_dou_ner.application"), (
                            f"{path} imports {module}"
                        )
