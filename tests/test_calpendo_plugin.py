"""
Unit and Integration Tests for Calpendo Data Source Plugin

Tests cover:
- Configuration validation (T016)
- Data transformation utilities (T018)
- Regex extraction
- Timezone conversion
- Status and resource mapping
- Full booking transformation
"""

import pytest
import os
import json
from datetime import datetime
from pathlib import Path
import pytz

from pylantir.data_sources.calpendo_plugin import CalendoPlugin
from pylantir.data_sources.base import PluginConfigError, PluginFetchError


# Load test fixtures
FIXTURES_PATH = Path(__file__).parent / "fixtures" / "calpendo_responses.json"
with open(FIXTURES_PATH) as f:
    FIXTURES = json.load(f)


class TestConfigValidation:
    """Test configuration validation (T016)"""

    def setup_method(self):
        """Set up test environment variables"""
        os.environ["CALPENDO_USERNAME"] = "test_user"
        os.environ["CALPENDO_PASSWORD"] = "test_pass"

    def teardown_method(self):
        """Clean up environment variables"""
        if "CALPENDO_USERNAME" in os.environ:
            del os.environ["CALPENDO_USERNAME"]
        if "CALPENDO_PASSWORD" in os.environ:
            del os.environ["CALPENDO_PASSWORD"]

    def test_valid_config_passes(self):
        """Valid configuration should pass validation"""
        plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T Diagnostic"],
            "field_mapping": {
                "patient_id": "title"
            }
        }

        is_valid, error = plugin.validate_config(config)
        assert is_valid is True
        assert error == ""

    def test_missing_base_url_fails(self):
        """Missing base_url should raise error"""
        plugin = CalendoPlugin()
        config = {
            "resources": ["3T Diagnostic"],
            "field_mapping": {}
        }

        is_valid, error = plugin.validate_config(config)
        assert is_valid is False
        assert "base_url" in error

    def test_empty_resources_fails(self):
        """Empty resources list should raise error"""
        plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": [],
            "field_mapping": {}
        }

        is_valid, error = plugin.validate_config(config)
        assert is_valid is False
        assert "resources" in error

    def test_missing_env_vars_fails(self):
        """Missing environment variables should raise error"""
        del os.environ["CALPENDO_USERNAME"]
        plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {}
        }

        is_valid, error = plugin.validate_config(config)
        assert is_valid is False
        assert "CALPENDO_USERNAME" in error or "CALPENDO_PASSWORD" in error

    def test_invalid_lookback_multiplier_fails(self):
        """Invalid lookback_multiplier type should raise error"""
        plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {},
            "lookback_multiplier": "invalid"
        }

        is_valid, error = plugin.validate_config(config)
        assert is_valid is False
        assert "lookback_multiplier" in error

    def test_invalid_timezone_fails(self):
        """Invalid timezone should raise error"""
        plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {},
            "timezone": "Invalid/Timezone"
        }

        is_valid, error = plugin.validate_config(config)
        assert is_valid is False
        assert "timezone" in error or "Invalid" in error

    def test_malformed_extract_pattern_fails(self):
        """Malformed _extract pattern should raise error"""
        plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {
                "patient_id": {
                    "source_field": "title",
                    "_extract": {
                        "group": 1
                        # Missing "pattern" key
                    }
                }
            }
        }

        is_valid, error = plugin.validate_config(config)
        assert is_valid is False
        assert "pattern" in error


class TestRegexExtraction:
    """Test regex field extraction (T018)"""

    def setup_method(self):
        os.environ["CALPENDO_USERNAME"] = "test"
        os.environ["CALPENDO_PASSWORD"] = "test"
        self.plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {}
        }
        self.plugin.validate_config(config)

    def teardown_method(self):
        if "CALPENDO_USERNAME" in os.environ:
            del os.environ["CALPENDO_USERNAME"]
        if "CALPENDO_PASSWORD" in os.environ:
            del os.environ["CALPENDO_PASSWORD"]

    def test_extract_patient_id_from_title(self):
        """Extract patient ID from 'SUB001_John_Doe' format"""
        extract_config = {
            "pattern": r"^([A-Z0-9]+)_.*",
            "group": 1
        }
        result = self.plugin._extract_field_with_regex("SUB001_John_Doe", extract_config)
        assert result == "SUB001"

    def test_extract_patient_name_from_title(self):
        """Extract patient name from 'SUB001_John_Doe' format"""
        extract_config = {
            "pattern": r"^[A-Z0-9]+_(.+)$",
            "group": 1
        }
        result = self.plugin._extract_field_with_regex("SUB001_John_Doe", extract_config)
        assert result == "John_Doe"

    def test_no_match_returns_original(self):
        """No regex match should return original value"""
        extract_config = {
            "pattern": r"^NOMATCH_.*",
            "group": 1
        }
        result = self.plugin._extract_field_with_regex("SUB001_John_Doe", extract_config)
        assert result == "SUB001_John_Doe"

    def test_invalid_regex_raises_error(self):
        """Invalid regex pattern should raise PluginConfigError"""
        extract_config = {
            "pattern": r"[invalid(regex",
            "group": 1
        }
        with pytest.raises(PluginConfigError):
            self.plugin._extract_field_with_regex("test", extract_config)

    def test_empty_source_value_returns_empty(self):
        """Empty source value should return empty string"""
        extract_config = {
            "pattern": r".*",
            "group": 0
        }
        result = self.plugin._extract_field_with_regex("", extract_config)
        assert result == ""


class TestTimezoneConversion:
    """Test timezone conversion utilities (T018)"""

    def setup_method(self):
        os.environ["CALPENDO_USERNAME"] = "test"
        os.environ["CALPENDO_PASSWORD"] = "test"
        self.plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {},
            "timezone": "America/Edmonton"
        }
        self.plugin.validate_config(config)

    def teardown_method(self):
        if "CALPENDO_USERNAME" in os.environ:
            del os.environ["CALPENDO_USERNAME"]
        if "CALPENDO_PASSWORD" in os.environ:
            del os.environ["CALPENDO_PASSWORD"]

    def test_parse_formatted_name(self):
        """Parse formattedName date range correctly"""
        formatted_name = "[2026-01-27 14:00:00.0, 2026-01-27 15:30:00.0]"
        start_dt, end_dt = self.plugin._parse_formatted_name_dates(formatted_name)

        assert start_dt.year == 2026
        assert start_dt.month == 1
        assert start_dt.day == 27
        assert start_dt.hour == 14
        assert start_dt.minute == 0

        assert end_dt.hour == 15
        assert end_dt.minute == 30

    def test_invalid_format_raises_error(self):
        """Invalid formattedName format should raise ValueError"""
        invalid_format = "Invalid format"
        with pytest.raises(ValueError):
            self.plugin._parse_formatted_name_dates(invalid_format)

    def test_convert_to_utc(self):
        """Convert Mountain Time to UTC correctly"""
        mt_tz = pytz.timezone("America/Edmonton")
        # January (MST, UTC-7)
        mt_time = mt_tz.localize(datetime(2026, 1, 27, 14, 0, 0))
        utc_time = self.plugin._convert_to_utc(mt_time)

        # 14:00 MST = 21:00 UTC
        assert utc_time.hour == 21
        assert utc_time.tzinfo == pytz.UTC

    def test_dst_transition_handled(self):
        """DST transitions should be handled correctly by pytz"""
        # March DST transition test
        mt_tz = pytz.timezone("America/Edmonton")
        # Before DST (MST, UTC-7)
        before_dst = mt_tz.localize(datetime(2026, 3, 8, 1, 0, 0))
        # After DST (MDT, UTC-6)
        after_dst = mt_tz.localize(datetime(2026, 3, 8, 3, 0, 0))

        utc_before = self.plugin._convert_to_utc(before_dst)
        utc_after = self.plugin._convert_to_utc(after_dst)

        # Verify UTC offset changed
        assert utc_before.hour == 8  # 1 AM MST = 8 AM UTC
        assert utc_after.hour == 9   # 3 AM MDT = 9 AM UTC


class TestStatusAndResourceMapping:
    """Test status and resource mapping (T018)"""

    def setup_method(self):
        os.environ["CALPENDO_USERNAME"] = "test"
        os.environ["CALPENDO_PASSWORD"] = "test"
        self.plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {},
            "resource_modality_mapping": {
                "3T": "MR",
                "EEG": "EEG"
            }
        }
        self.plugin.validate_config(config)

    def teardown_method(self):
        if "CALPENDO_USERNAME" in os.environ:
            del os.environ["CALPENDO_USERNAME"]
        if "CALPENDO_PASSWORD" in os.environ:
            del os.environ["CALPENDO_PASSWORD"]

    def test_map_all_known_statuses(self):
        """All known Calpendo statuses should map correctly"""
        assert self.plugin._map_status_to_dicom("Approved") == "SCHEDULED"
        assert self.plugin._map_status_to_dicom("In Progress") == "IN_PROGRESS"
        assert self.plugin._map_status_to_dicom("Completed") == "COMPLETED"
        assert self.plugin._map_status_to_dicom("Cancelled") == "DISCONTINUED"
        assert self.plugin._map_status_to_dicom("Pending") == "SCHEDULED"

    def test_unknown_status_defaults_to_scheduled(self):
        """Unknown status should default to SCHEDULED"""
        assert self.plugin._map_status_to_dicom("Unknown Status") == "SCHEDULED"

    def test_resource_prefix_match(self):
        """Resource name should match by prefix"""
        assert self.plugin._map_resource_to_modality("3T Diagnostic") == "MR"
        assert self.plugin._map_resource_to_modality("3T Research") == "MR"
        assert self.plugin._map_resource_to_modality("EEG Lab") == "EEG"

    def test_resource_exact_match(self):
        """Exact resource name should match first"""
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {},
            "resource_modality_mapping": {
                "3T Diagnostic": "MR_EXACT",
                "3T": "MR_PREFIX"
            }
        }
        plugin = CalendoPlugin()
        plugin.validate_config(config)
        assert plugin._map_resource_to_modality("3T Diagnostic") == "MR_EXACT"

    def test_unmapped_resource_returns_original(self):
        """Unmapped resource should return original name"""
        assert self.plugin._map_resource_to_modality("Unknown Scanner") == "Unknown Scanner"


class TestBookingTransformation:
    """Test full booking transformation (T018)"""

    def setup_method(self):
        os.environ["CALPENDO_USERNAME"] = "test"
        os.environ["CALPENDO_PASSWORD"] = "test"
        self.plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {
                "patient_id": {
                    "source_field": "title",
                    "_extract": {
                        "pattern": r"^([A-Z0-9]+)_.*",
                        "group": 1
                    }
                },
                "patient_name": {
                    "source_field": "title",
                    "_extract": {
                        "pattern": r"^[A-Z0-9]+_(.+)$",
                        "group": 1
                    }
                },
                "study_description": {
                    "source_field": "properties.project.formattedName",
                    "_extract": {
                        "pattern": r"^([^(]+)",
                        "group": 1
                    }
                },
                "accession_number": "id"
            },
            "resource_modality_mapping": {
                "3T": "MR"
            },
            "timezone": "America/Edmonton"
        }
        self.plugin.validate_config(config)

    def teardown_method(self):
        if "CALPENDO_USERNAME" in os.environ:
            del os.environ["CALPENDO_USERNAME"]
        if "CALPENDO_PASSWORD" in os.environ:
            del os.environ["CALPENDO_PASSWORD"]

    def test_transform_complete_booking(self):
        """Transform complete booking with all fields"""
        booking = FIXTURES["booking_detail_12345"]
        field_mapping = self.plugin._config["field_mapping"]

        entry = self.plugin._transform_booking_to_entry(booking, field_mapping)

        assert entry is not None
        assert entry["patient_id"] == "SUB001"
        assert entry["patient_name"] == "John_Doe"
        assert "BRISKP" in entry["study_description"]
        assert entry["accession_number"] == "12345"
        assert entry["modality"] == "MR"
        assert entry["performed_procedure_step_status"] == "SCHEDULED"
        assert "scheduled_start_date" in entry
        assert "scheduled_start_time" in entry
        assert "scheduled_procedure_step_duration" in entry
        assert "booking_hash" in entry["notes"]

    def test_transform_with_missing_optional_fields(self):
        """Transform booking with missing optional fields"""
        booking = {
            "id": 99999,
            "formattedName": "[2026-01-27 14:00:00.0, 2026-01-27 15:00:00.0]",
            "title": "SUB999_Test_User",
            "status": "Approved",
            "properties": {}
        }
        field_mapping = self.plugin._config["field_mapping"]

        entry = self.plugin._transform_booking_to_entry(booking, field_mapping)

        # Should succeed with required fields
        assert entry is not None
        assert entry["patient_id"] == "SUB999"

    def test_missing_required_field_returns_none(self):
        """Booking missing required field should return None"""
        booking = {
            "id": 99999,
            "formattedName": "[2026-01-27 14:00:00.0, 2026-01-27 15:00:00.0]",
            # Missing title (required for patient_id)
            "status": "Approved"
        }
        field_mapping = self.plugin._config["field_mapping"]

        entry = self.plugin._transform_booking_to_entry(booking, field_mapping)

        # Should return None due to missing required field
        assert entry is None


class TestChangeDetection:
    """Test booking hash computation (T018)"""

    def setup_method(self):
        os.environ["CALPENDO_USERNAME"] = "test"
        os.environ["CALPENDO_PASSWORD"] = "test"
        self.plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {}
        }
        self.plugin.validate_config(config)

    def teardown_method(self):
        if "CALPENDO_USERNAME" in os.environ:
            del os.environ["CALPENDO_USERNAME"]
        if "CALPENDO_PASSWORD" in os.environ:
            del os.environ["CALPENDO_PASSWORD"]

    def test_same_booking_produces_same_hash(self):
        """Same booking data should produce same hash"""
        booking = FIXTURES["booking_detail_12345"]
        hash1 = self.plugin._compute_booking_hash(booking)
        hash2 = self.plugin._compute_booking_hash(booking)
        assert hash1 == hash2

    def test_changed_title_produces_different_hash(self):
        """Changed title should produce different hash"""
        booking1 = FIXTURES["booking_detail_12345"].copy()
        booking2 = FIXTURES["booking_detail_12345"].copy()
        booking2["title"] = "SUB999_Different_Name"

        hash1 = self.plugin._compute_booking_hash(booking1)
        hash2 = self.plugin._compute_booking_hash(booking2)
        assert hash1 != hash2

    def test_changed_status_produces_different_hash(self):
        """Changed status should produce different hash"""
        booking1 = FIXTURES["booking_detail_12345"].copy()
        booking2 = FIXTURES["booking_detail_12345"].copy()
        booking2["status"] = "Cancelled"

        hash1 = self.plugin._compute_booking_hash(booking1)
        hash2 = self.plugin._compute_booking_hash(booking2)
        assert hash1 != hash2

    def test_hash_stored_in_notes(self):
        """Hash should be stored correctly in notes JSON"""
        booking = FIXTURES["booking_detail_12345"]
        field_mapping = {
            "patient_id": "title",
            "accession_number": "id"
        }

        entry = self.plugin._transform_booking_to_entry(booking, field_mapping)

        assert "notes" in entry
        notes = json.loads(entry["notes"])
        assert "booking_hash" in notes
        assert len(notes["booking_hash"]) == 64  # SHA256 hex length
