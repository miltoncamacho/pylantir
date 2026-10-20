from unittest.mock import patch

from pylantir.data_sources.redcap_plugin import REDCapPlugin


def _plugin():
    plugin = REDCapPlugin()
    plugin._site_id = "792"
    return plugin


def test_neuro_pcp_prefixes_study_id_in_patient_id():
    entries = _plugin()._transform_records(
        [{
            "study_id": "sub-123",
            "family_id": "fam-456",
            "mri_instance": "2",
            "neuro_pcp": "1",
            "mri_date": "2026-10-19",
            "mri_time": "10:30",
        }],
        {},
    )

    assert entries[0]["patient_id"] == "sub_n_123_ses_2_fam_456_site_792"
    assert entries[0]["patient_name"] == "cpip-id-123^fa-456"


def test_non_neuro_pcp_uses_mri_instance_in_patient_id():
    entries = _plugin()._transform_records(
        [{
            "study_id": "123",
            "family_id": "456",
            "mri_instance": "2",
            "neuro_pcp": "0",
            "mri_date": "2026-10-19",
            "mri_time": "10:30",
        }],
        {},
    )

    assert entries[0]["patient_id"] == "sub_123_ses_2_fam_456_site_792"


def test_fetch_entries_always_requests_neuro_pcp_field():
    plugin = _plugin()

    with patch.object(plugin, "_fetch_redcap_entries", return_value=[]) as fetch:
        plugin.fetch_entries({}, 60)

    requested_fields = fetch.call_args.args[0]
    assert "neuro_pcp" in requested_fields
