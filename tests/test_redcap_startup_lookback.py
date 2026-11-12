from unittest.mock import patch

import pytest

from pylantir.data_sources.base import PluginFetchError
from pylantir.data_sources.redcap_plugin import REDCapPlugin
from pylantir.data_sources.redcap_concussion_plugin import ConcussionREDCapPlugin


@pytest.fixture(params=[REDCapPlugin, ConcussionREDCapPlugin])
def plugin(request, monkeypatch):
    instance = request.param()
    monkeypatch.setenv(instance.API_URL_ENV, "https://example.org/api/")
    monkeypatch.setenv(instance.API_TOKEN_ENV, "test-token")
    return instance


def configure(plugin, **settings):
    return plugin.validate_config({"site": "792", "protocol": "MRI", **settings})


@pytest.mark.parametrize("hours", [72, 0.5])
def test_startup_window_then_normal_interval(plugin, hours):
    assert configure(plugin, startup_lookback_hours=hours) == (True, "")
    with patch.object(plugin, "_fetch_redcap_entries", return_value=[]) as fetch:
        plugin.fetch_entries({}, 60)
        plugin.fetch_entries({}, 360)
    assert [call.args[1] for call in fetch.call_args_list] == [hours * 3600, 360]


def test_omitted_setting_preserves_supplied_intervals(plugin):
    assert configure(plugin) == (True, "")
    with patch.object(plugin, "_fetch_redcap_entries", return_value=[]) as fetch:
        plugin.fetch_entries({}, 60)
        plugin.fetch_entries({}, 360)
    assert [call.args[1] for call in fetch.call_args_list] == [60, 360]


def test_failed_startup_fetch_retries_window(plugin):
    assert configure(plugin, startup_lookback_hours=72) == (True, "")
    with patch.object(plugin, "_fetch_redcap_entries", side_effect=[RuntimeError("offline"), [], []]) as fetch:
        with pytest.raises(PluginFetchError):
            plugin.fetch_entries({}, 60)
        plugin.fetch_entries({}, 360)
        plugin.fetch_entries({}, 360)
    assert [call.args[1] for call in fetch.call_args_list] == [259200, 259200, 360]


@pytest.mark.parametrize("hours", [0, -1, True, "72", None, float("inf"), float("nan")])
def test_invalid_startup_window(plugin, hours):
    valid, error = configure(plugin, startup_lookback_hours=hours)
    assert not valid
    assert "startup_lookback_hours" in error
