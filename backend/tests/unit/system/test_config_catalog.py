"""K2: a misspelt setting fails startup, and the example file lists every setting."""

import pytest
from app.core.config import settings as config_settings
from app.core.config.catalog import catalog, main, render_example, unknown_keys
from app.core.config.settings import Settings, check_known_keys

REQUIRED = {"database_password": "x", "business_database_password": "y"}


def _env_file(tmp_path, text):
    path = tmp_path / "settings.env"
    path.write_text(text, encoding="utf-8")
    return path


def test_example_file_matches_the_catalog():
    assert main(["--check"]) == 0


def test_catalog_lists_every_setting_once():
    names = [item.env for item in catalog()]

    assert len(names) == len(set(names)) == len(Settings.model_fields)
    assert set(names) == {field.upper() for field in Settings.model_fields}


def test_secrets_have_no_value_in_the_example():
    secrets = [item for item in catalog() if item.secret]
    example = render_example()

    assert {item.env for item in secrets} >= {"DATABASE_PASSWORD", "DEEPSEEK_API_KEY"}
    assert "DEEPSEEK_API_KEY=\n" in example
    assert "OPENAI_API_KEY=\n" in example


def test_unknown_keys_finds_typos_but_not_unrelated_variables():
    found = unknown_keys(
        ["RAG_RERANK_TOPK", "DATABASE_HOST", "ACME_DEMO_DATABASE_PASSWORD"],
        {"PATH": "/bin", "HOME": "/root", "LLM_MODLE": "x", "LLM_MODEL": "y"},
        credential_names=["ACME_DEMO_DATABASE_PASSWORD"],
    )

    assert found == ["LLM_MODLE", "RAG_RERANK_TOPK"]


def test_misspelt_setting_fails_startup_in_production(tmp_path):
    settings = Settings(**REQUIRED, app_env="production", jwt_secret="a-real-secret")
    env_file = _env_file(tmp_path, "RAG_RERANK_TOPK=secret-looking-value\n")

    with pytest.raises(ValueError, match="RAG_RERANK_TOPK") as raised:
        check_known_keys(settings, env_file=env_file, environ={})

    assert "secret-looking-value" not in str(raised.value)


def test_misspelt_setting_only_warns_in_development(tmp_path, monkeypatch):
    # Other tests reconfigure logging, so capture the module logger directly.
    warnings = []
    monkeypatch.setattr(config_settings.logger, "warning", warnings.append)
    settings = Settings(**REQUIRED, app_env="development")
    env_file = _env_file(tmp_path, "DATABASE_HOST=db\n")

    unknown = check_known_keys(
        settings, env_file=env_file, environ={"RAG_RERANK_TOPK": "secret-ish"}
    )

    assert unknown == ["RAG_RERANK_TOPK"]
    assert len(warnings) == 1
    assert "RAG_RERANK_TOPK" in warnings[0]
    assert "secret-ish" not in warnings[0]


def test_known_settings_pass(tmp_path):
    settings = Settings(**REQUIRED, app_env="production", jwt_secret="a-real-secret")
    env_file = _env_file(tmp_path, "RAG_RERANK_TOP_K=1\n")

    assert check_known_keys(settings, env_file=env_file, environ={}) == []
