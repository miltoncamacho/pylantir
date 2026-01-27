"""
Integration Tests for Calpendo Data Source Plugin with Mock API

Tests cover:
- Full fetch workflow with mocked API responses (T017)
- API authentication failures (T017)
- Empty booking results (T017)
- Deleted booking handling (T017)
- End-to-end sync workflow (T020)
"""

import pytest
import os
import json
import re
from pathlib import Path
from datetime import datetime
import responses
import pytz

from pylantir.data_sources.calpendo_plugin import CalendoPlugin
from pylantir.data_sources.base import PluginFetchError


# Load test fixtures
FIXTURES_PATH = Path(__file__).parent / "fixtures" / "calpendo_responses.json"
with open(FIXTURES_PATH) as f:
    FIXTURES = json.load(f)


@pytest.fixture
def calpendo_config():
    """Standard Calpendo configuration for tests"""
    return {
        "base_url": "https://test.calpendo.com",
        "resources": ["3T Diagnostic", "EEG Lab"],
        "status_filter": "Approved",
        "lookback_multiplier": 2,
        "timezone": "America/Edmonton",
        "resource_modality_mapping": {
            "3T": "MR",
            "EEG": "EEG"
        },
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
        }
    }


@pytest.fixture
def plugin_with_env(calpendo_config):
    """Create plugin with environment variables set"""
    os.environ["CALPENDO_USERNAME"] = "test_user"
    os.environ["CALPENDO_PASSWORD"] = "test_pass"
    
    plugin = CalendoPlugin()
    plugin.validate_config(calpendo_config)
    
    yield plugin
    
    # Cleanup
    if "CALPENDO_USERNAME" in os.environ:
        del os.environ["CALPENDO_USERNAME"]
    if "CALPENDO_PASSWORD" in os.environ:
        del os.environ["CALPENDO_PASSWORD"]


class TestAPIIntegration:
    """Test API integration with mocked responses (T017)"""

    @responses.activate
    def test_successful_fetch_workflow(self, plugin_with_env, calpendo_config):
        """Test successful full fetch workflow"""
        # Mock booking query - use regex URL matching
        responses.add(
            responses.GET,
            re.compile(r".*/webdav/q/Calpendo\.Booking/.*"),
            json=FIXTURES["booking_query_response"],
            status=200
        )

        # Mock booking details
        responses.add(
            responses.GET,
            "https://test.calpendo.com/webdav/b/Calpendo.Booking/12345",
            json=FIXTURES["booking_detail_12345"],
            status=200
        )
        responses.add(
            responses.GET,
            "https://test.calpendo.com/webdav/b/Calpendo.Booking/12346",
            json=FIXTURES["booking_detail_12346"],
            status=200
        )
        responses.add(
            responses.GET,
            "https://test.calpendo.com/webdav/b/Calpendo.Booking/12347",
            json=FIXTURES["booking_detail_12347"],
            status=200
        )

        # Mock MRI operator fetch
        responses.add(
            responses.GET,
            re.compile(r".*/webdav/q/MRIScan/.*"),
            json=FIXTURES["mri_operator_12345"],
            status=200
        )

        # Execute fetch_entries
        entries = plugin_with_env.fetch_entries(
            field_mapping=calpendo_config["field_mapping"],
            interval=60
        )

        # Verify results
        assert len(entries) == 3  # All 3 bookings returned
        assert entries[0]["patient_id"] == "SUB001"
        assert entries[1]["patient_id"] == "SUB002"
        assert entries[2]["patient_id"] == "SUB003"

    @responses.activate
    def test_authentication_failure(self, plugin_with_env, calpendo_config):
        """Test API authentication failure raises PluginFetchError"""
        # Mock 401 Unauthorized
        responses.add(
            responses.GET,
            re.compile(r".*/webdav/q/Calpendo\.Booking/.*"),
            json={"error": "Unauthorized"},
            status=401
        )

        # Should raise PluginFetchError
        with pytest.raises(PluginFetchError) as exc_info:
            plugin_with_env.fetch_entries(
                field_mapping=calpendo_config["field_mapping"],
                interval=60
            )
        
        assert "authentication" in str(exc_info.value).lower()

    @responses.activate
    def test_empty_booking_results(self, plugin_with_env, calpendo_config):
        """Test empty booking results returns empty list"""
        # Mock empty response
        responses.add(
            responses.GET,
            re.compile(r".*/webdav/q/Calpendo\.Booking/.*"),
            json={"biskits": []},
            status=200
        )

        entries = plugin_with_env.fetch_entries(
            field_mapping=calpendo_config["field_mapping"],
            interval=60
        )

        assert entries == []

    @responses.activate
    def test_deleted_booking_handling(self, plugin_with_env, calpendo_config):
        """Test that deleted bookings (404) are filtered out"""
        # Mock booking query with 2 bookings
        responses.add(
            responses.GET,
            re.compile(r".*/webdav/q/Calpendo\.Booking/.*"),
            json={
                "biskits": [
                    {"id": 12345},
                    {"id": 99999}  # This one will return 404
                ]
            },
            status=200
        )

        # Mock first booking success
        responses.add(
            responses.GET,
            "https://test.calpendo.com/webdav/b/Calpendo.Booking/12345",
            json=FIXTURES["booking_detail_12345"],
            status=200
        )

        # Mock second booking as deleted (404)
        responses.add(
            responses.GET,
            "https://test.calpendo.com/webdav/b/Calpendo.Booking/99999",
            json={"error": "Not Found"},
            status=404
        )

        # Mock MRI operator fetch
        responses.add(
            responses.GET,
            re.compile(r".*/webdav/q/MRIScan/.*"),
            json=FIXTURES["mri_operator_12345"],
            status=200
        )

        entries = plugin_with_env.fetch_entries(
            field_mapping=calpendo_config["field_mapping"],
            interval=60
        )

        # Should only return 1 entry (404 filtered out)
        assert len(entries) == 1
        assert entries[0]["patient_id"] == "SUB001"

    @responses.activate
    def test_parallel_detail_fetching(self, plugin_with_env, calpendo_config):
        """Test parallel detail fetching performance"""
        # Mock booking query with multiple bookings
        booking_ids = list(range(12345, 12355))  # 10 bookings
        responses.add(
            responses.GET,
            re.compile(r".*/webdav/q/Calpendo\.Booking/.*"),
            json={"biskits": [{"id": bid} for bid in booking_ids]},
            status=200
        )

        # Mock all booking details
        for bid in booking_ids:
            responses.add(
                responses.GET,
                f"https://test.calpendo.com/webdav/b/Calpendo.Booking/{bid}",
                json={
                    "id": bid,
                    "formattedName": "[2026-01-27 14:00:00.0, 2026-01-27 15:00:00.0]",
                    "title": f"SUB{bid}_Test_User",
                    "status": "Approved",
                    "biskitType": "EEGScan",
                    "properties": {
                        "project": {"formattedName": "Test Study"},
                        "resource": {"formattedName": "EEG Lab"}
                    }
                },
                status=200
            )

        # Execute fetch
        entries = plugin_with_env.fetch_entries(
            field_mapping=calpendo_config["field_mapping"],
            interval=60
        )

        # Should return all 10 entries
        assert len(entries) == 10


class TestQueryConstruction:
    """Test query string construction"""

    def setup_method(self):
        os.environ["CALPENDO_USERNAME"] = "test"
        os.environ["CALPENDO_PASSWORD"] = "test"

    def teardown_method(self):
        if "CALPENDO_USERNAME" in os.environ:
            del os.environ["CALPENDO_USERNAME"]
        if "CALPENDO_PASSWORD" in os.environ:
            del os.environ["CALPENDO_PASSWORD"]

    def test_single_resource_query(self):
        """Test query with single resource"""
        plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T Diagnostic"],
            "field_mapping": {},
            "timezone": "America/Edmonton"
        }
        plugin.validate_config(config)

        tz = pytz.timezone("America/Edmonton")
        start = tz.localize(datetime(2026, 1, 27, 10, 0, 0))
        end = tz.localize(datetime(2026, 1, 28, 10, 0, 0))

        query = plugin._build_booking_query(start, end)

        assert "OR/resource.name/EQ/3T Diagnostic" in query
        assert "dateRange.start/GE/" in query
        assert "dateRange.start/LT/" in query

    def test_multiple_resources_query(self):
        """Test query with multiple resources uses OR logic"""
        plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T Diagnostic", "EEG Lab"],
            "field_mapping": {},
            "timezone": "America/Edmonton"
        }
        plugin.validate_config(config)

        tz = pytz.timezone("America/Edmonton")
        start = tz.localize(datetime(2026, 1, 27, 10, 0, 0))
        end = tz.localize(datetime(2026, 1, 28, 10, 0, 0))

        query = plugin._build_booking_query(start, end)

        assert "OR/" in query
        assert "resource.name/EQ/3T Diagnostic" in query
        assert "resource.name/EQ/EEG Lab" in query

    def test_status_filter_query(self):
        """Test query with status filter uses AND logic"""
        plugin = CalendoPlugin()
        config = {
            "base_url": "https://test.calpendo.com",
            "resources": ["3T"],
            "field_mapping": {},
            "status_filter": "Approved",
            "timezone": "America/Edmonton"
        }
        plugin.validate_config(config)

        tz = pytz.timezone("America/Edmonton")
        start = tz.localize(datetime(2026, 1, 27, 10, 0, 0))
        end = tz.localize(datetime(2026, 1, 28, 10, 0, 0))

        query = plugin._build_booking_query(start, end)

        assert "status/EQ/Approved" in query
        assert "AND/" in query


class TestEndToEnd:
    """End-to-end integration test (T020)"""

    @responses.activate
    def test_complete_sync_workflow(self, calpendo_config):
        """Test complete sync workflow with change detection"""
        os.environ["CALPENDO_USERNAME"] = "test_user"
        os.environ["CALPENDO_PASSWORD"] = "test_pass"

        # First sync
        plugin1 = CalendoPlugin()
        plugin1.validate_config(calpendo_config)

        # Mock API responses
        responses.add(
            responses.GET,
            re.compile(r".*/webdav/q/Calpendo\.Booking/.*"),
            json=FIXTURES["booking_query_response"],
            status=200
        )
        responses.add(
            responses.GET,
            "https://test.calpendo.com/webdav/b/Calpendo.Booking/12345",
            json=FIXTURES["booking_detail_12345"],
            status=200
        )
        responses.add(
            responses.GET,
            "https://test.calpendo.com/webdav/b/Calpendo.Booking/12346",
            json=FIXTURES["booking_detail_12346"],
            status=200
        )
        responses.add(
            responses.GET,
            "https://test.calpendo.com/webdav/b/Calpendo.Booking/12347",
            json=FIXTURES["booking_detail_12347"],
            status=200
        )
        responses.add(
            responses.GET,
            re.compile(r".*/webdav/q/MRIScan/.*"),
            json=FIXTURES["mri_operator_12345"],
            status=200
        )

        # First fetch
        entries1 = plugin1.fetch_entries(
            field_mapping=calpendo_config["field_mapping"],
            interval=60
        )

        # Verify first sync
        assert len(entries1) == 3
        assert entries1[0]["patient_id"] == "SUB001"
        assert entries1[0]["modality"] == "MR"
        assert entries1[0]["performed_procedure_step_status"] == "SCHEDULED"
        assert "scheduled_start_date" in entries1[0]
        assert "scheduled_start_time" in entries1[0]
        assert "scheduled_procedure_step_duration" in entries1[0]
        
        # Verify hash is present
        notes1 = json.loads(entries1[0]["notes"])
        assert "booking_hash" in notes1
        
        # Clean up
        del os.environ["CALPENDO_USERNAME"]
        del os.environ["CALPENDO_PASSWORD"]
