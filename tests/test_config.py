from core.config import Settings


def test_legacy_postgres_url_is_normalized():
    settings = Settings(
        database_url="postgres://user:password@localhost:5432/aquatrace"
    )

    assert (
        settings.database_url == "postgresql://user:password@localhost:5432/aquatrace"
    )


def test_postgresql_url_remains_unchanged():
    database_url = "postgresql://user:password@localhost:5432/aquatrace"

    settings = Settings(database_url=database_url)

    assert settings.database_url == database_url


def test_sqlite_url_remains_unchanged():
    database_url = "sqlite:///:memory:"

    settings = Settings(database_url=database_url)

    assert settings.database_url == database_url
