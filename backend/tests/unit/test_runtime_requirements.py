import tomllib
from pathlib import Path


def test_ocrmypdf_is_declared_for_runtime() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    assert any("ocrmypdf" in dependency.lower() for dependency in dependencies)


def test_schema_migration_exists_for_384d_embeddings() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0004_fix_embedding_dimension.py"
    )
    assert migration_path.exists()
    text = migration_path.read_text(encoding="utf-8")
    assert "vector(384)" in text.lower()


def test_relative_storage_roots_are_project_scoped() -> None:
    from app.core.config import PROJECT_ROOT, get_settings

    settings = get_settings()
    assert settings.reference_root == (PROJECT_ROOT / "storage" / "reference").resolve()
    assert settings.archive_root == (PROJECT_ROOT / "storage" / "archive").resolve()


def test_embedding_health_check_does_not_load_or_download_model(monkeypatch) -> None:
    import huggingface_hub

    from app.services import embeddings

    class StubProvider:
        provider = "stub"
        model = "stub/model"
        dimension = 384

    monkeypatch.setattr(embeddings, "get_embedding_provider", lambda: StubProvider())
    monkeypatch.setattr(
        huggingface_hub, "try_to_load_from_cache", lambda *_args: "/cached/modules.json"
    )
    ready, detail = embeddings.check_embedding_provider()

    assert ready is True
    assert detail == "stub/stub/model/384"
