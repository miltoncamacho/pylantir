from unittest.mock import patch

from pylantir.data_sources import get_plugin
from pylantir.data_sources.redcap_concussion_plugin import ConcussionREDCapPlugin


def test_concussion_plugin_is_registered():
    assert get_plugin("redcap_concussion") is ConcussionREDCapPlugin


def test_concussion_plugin_uses_its_own_environment(monkeypatch):
    monkeypatch.setenv("REDCAP_API_URL", "https://main.example/api/")
    monkeypatch.setenv("REDCAP_API_TOKEN", "main-token")
    monkeypatch.setenv("REDCAP_API_URL_CONCUSSION", "https://concussion.example/api/")
    monkeypatch.setenv("REDCAP_API_TOKEN_CONCUSSION", "concussion-token")

    plugin = ConcussionREDCapPlugin()
    valid, error = plugin.validate_config({"site": "792", "protocol": "BRAIN_MRI_3T"})

    assert valid is True
    assert error == ""
    assert plugin._api_url == "https://concussion.example/api/"
    assert plugin._api_token == "concussion-token"


def test_concussion_plugin_reports_missing_concussion_credentials(monkeypatch):
    monkeypatch.setenv("REDCAP_API_URL", "https://main.example/api/")
    monkeypatch.setenv("REDCAP_API_TOKEN", "main-token")
    monkeypatch.delenv("REDCAP_API_URL_CONCUSSION", raising=False)
    monkeypatch.delenv("REDCAP_API_TOKEN_CONCUSSION", raising=False)

    valid, error = ConcussionREDCapPlugin().validate_config(
        {"site": "792", "protocol": "BRAIN_MRI_3T"}
    )

    assert valid is False
    assert error == "REDCAP_API_URL_CONCUSSION environment variable not set"


def test_concussion_fetch_connects_with_concussion_credentials(monkeypatch):
    monkeypatch.setenv("REDCAP_API_URL_CONCUSSION", "https://concussion.example/api/")
    monkeypatch.setenv("REDCAP_API_TOKEN_CONCUSSION", "concussion-token")
    plugin = ConcussionREDCapPlugin()
    plugin.validate_config({"site": "792", "protocol": "BRAIN_MRI_3T"})

    with patch("pylantir.data_sources.redcap_plugin.Project") as project_class:
        project = project_class.return_value
        project.export_metadata.return_value = []
        assert plugin._fetch_redcap_entries(["study_id"], 60) == []

    project_class.assert_called_once_with(
        "https://concussion.example/api/", "concussion-token"
    )


def test_concussion_plugin_rejects_invalid_mwl_days_ahead(monkeypatch):
    monkeypatch.setenv("REDCAP_API_URL_CONCUSSION", "https://concussion.example/api/")
    monkeypatch.setenv("REDCAP_API_TOKEN_CONCUSSION", "concussion-token")

    valid, error = ConcussionREDCapPlugin().validate_config(
        {"site": "792", "protocol": "BRAIN_MRI_3T", "mwl_days_ahead": -1}
    )

    assert valid is False
    assert error == "mwl_days_ahead must be an integer zero or greater"
