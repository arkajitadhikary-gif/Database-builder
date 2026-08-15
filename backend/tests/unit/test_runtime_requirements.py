from pathlib import Path
import tomllib


def test_ocrmypdf_is_declared_for_runtime() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    assert any("ocrmypdf" in dependency.lower() for dependency in dependencies)


def test_schema_migration_exists_for_384d_embeddings() -> None:
    migration_path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0004_fix_embedding_dimension.py"
    assert migration_path.exists()
    text = migration_path.read_text(encoding="utf-8")
    assert "vector(384)" in text.lower()
