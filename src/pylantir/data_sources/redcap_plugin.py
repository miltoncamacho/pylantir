"""
REDCap Data Source Plugin

This module implements the DataSourcePlugin interface for REDCap API integration.
Extracts and transforms REDCap data into DICOM worklist entries.

Version: 1.0.0
"""

import os
import logging
import re
from redcap.project import Project  # type: ignore
import uuid
from datetime import datetime, timedelta
import gc
from typing import Dict, List, Tuple

from .base import DataSourcePlugin, PluginFetchError, PluginConfigError

lgr = logging.getLogger(__name__)


class REDCapPlugin(DataSourcePlugin):
    """
    REDCap data source plugin.

    Connects to REDCap API and fetches worklist entries with memory-efficient
    processing (avoiding pandas DataFrames).

    Configuration Requirements:
        - site_id: Site identifier
        - protocol: Protocol mapping dictionary

    Environment Variables:
        - REDCAP_API_URL: REDCap API endpoint
        - REDCAP_API_TOKEN: REDCap API access token
    """

    def __init__(self):
        super().__init__()
        self._api_url = None
        self._api_token = None
        self._site_id = None
        self._protocol = None

    def validate_config(self, config: Dict) -> Tuple[bool, str]:
        """Validate REDCap plugin configuration."""
        # Check required config keys
        if "site_id" not in config:
            return (False, "Missing required configuration key: site_id")

        if "protocol" not in config:
            return (False, "Missing required configuration key: protocol")

        # Protocol can be either a string (protocol name) or dict (legacy format)
        if not isinstance(config["protocol"], (str, dict)):
            return (False, "protocol must be a string or dictionary")

        # Check environment variables
        self._api_url = os.getenv("REDCAP_API_URL")
        self._api_token = os.getenv("REDCAP_API_TOKEN")

        if not self._api_url:
            return (False, "REDCAP_API_URL environment variable not set")

        if not self._api_token:
            return (False, "REDCAP_API_TOKEN environment variable not set")

        self._site_id = config.get("site_id")
        self._protocol = config.get("protocol")

        self.logger.info(f"REDCap plugin validated for site {config['site_id']}")
        return (True, "")

    def fetch_entries(
        self,
        field_mapping: Dict[str, str],
        interval: float
    ) -> List[Dict]:
        """
        Fetch worklist entries from REDCap.

        Uses incremental sync based on interval parameter to fetch only
        recently modified records.
        """
        try:
            # Extract REDCap field names from mapping
            redcap_fields = list(field_mapping.keys())

            # Ensure required REDCap fields are included
            default_fields = [
                "record_id", "study_id", "redcap_repeat_instrument",
                "mri_instance", "mri_date", "mri_time", "family_id",
                "youth_dob_y", "demo_sex"
            ]
            for field in default_fields:
                if field not in redcap_fields:
                    redcap_fields.append(field)

            # Fetch from REDCap API
            raw_records = self._fetch_redcap_entries(redcap_fields, interval)

            # Transform to WorklistItem format
            entries = self._transform_records(raw_records, field_mapping)

            self.logger.info(f"Fetched {len(entries)} worklist entries from REDCap")
            return entries

        except Exception as e:
            raise PluginFetchError(f"Failed to fetch REDCap data: {e}") from e

    def _fetch_redcap_entries(self, redcap_fields: List[str], interval: float) -> List[Dict]:
        """
        Fetch REDCap entries using PyCap with memory-efficient processing.

        MEMORY OPTIMIZATION: Uses format_type="json" instead of "df" to avoid
        creating large pandas DataFrames (50-100x memory reduction).
        """
        project = Project(self._api_url, self._api_token)

        try:
            # Fetch metadata to get valid REDCap field names
            valid_fields = {field["field_name"] for field in project.export_metadata()}
            redcap_fields = [field for field in redcap_fields if field in valid_fields]

            if not redcap_fields:
                self.logger.error("No valid REDCap fields found in provided mapping")
                return []

            self.logger.info(f"Fetching REDCap data for fields: {redcap_fields}")

            # Calculate date range for incremental sync
            datetime_now = datetime.now()
            datetime_interval = datetime_now - timedelta(seconds=interval)

            # Export data as JSON (list of dicts) instead of DataFrame
            records = project.export_records(
                fields=redcap_fields,
                date_begin=datetime_interval,
                date_end=datetime_now,
                format_type="json"
            )

        finally:
            # Clean up PyCap Project immediately after export
            del project
            gc.collect()

        if not records:
            self.logger.warning("No records retrieved from REDCap")
            return []

        self.logger.info(f"Retrieved {len(records)} raw records from REDCap")

        # Filter for valid MRI records
        filtered_records = self._filter_mri_records(records, redcap_fields)

        # Clean up intermediate data
        del records
        gc.collect()

        return filtered_records

    def _filter_mri_records(
        self,
        records: List[Dict],
        redcap_fields: List[str]
    ) -> List[Dict]:
        """
        Filter and group REDCap records to extract valid MRI entries.

        Groups by record_id and merges baseline + MRI instrument data.
        """
        # Group records by record_id using native Python
        records_by_id = {}
        for record in records:
            record_id = record.get('record_id')
            if record_id not in records_by_id:
                records_by_id[record_id] = []
            records_by_id[record_id].append(record)

        filtered_records = []

        # Process each record_id group
        for record_id, group in records_by_id.items():
            # Find baseline (non-repeated instrument) values
            baseline_record = None
            for rec in group:
                if not rec.get('redcap_repeat_instrument'):
                    baseline_record = rec
                    break

            if baseline_record is None:
                baseline_record = {}

            # Filter for valid MRI rows only
            mri_rows = [
                rec for rec in group
                if rec.get('redcap_repeat_instrument') == 'mri'
                and rec.get('mri_instance')
                and rec.get('mri_instance') != ''
                and rec.get('mri_date')
                and rec.get('mri_time')
            ]

            for mri_row in mri_rows:
                record = {"record_id": record_id}

                # Merge fields from baseline and mri_row
                for field in redcap_fields:
                    # Use MRI row value if present, otherwise baseline
                    if field in mri_row and mri_row[field] not in (None, '', 'NaN'):
                        record[field] = mri_row[field]
                    elif field in baseline_record:
                        record[field] = baseline_record[field]
                    else:
                        record[field] = None

                filtered_records.append(record)

        # Clean up intermediate data
        del records_by_id
        gc.collect()

        self.logger.info(f"Filtered to {len(filtered_records)} MRI records")
        return filtered_records

    def _transform_records(
        self,
        raw_records: List[Dict],
        field_mapping: Dict[str, str]
    ) -> List[Dict]:
        """
        Transform REDCap records to WorklistItem format.

        Applies field mapping and constructs DICOM-compliant identifiers.
        """
        entries = []

        for record in raw_records:
            # Extract core identifiers
            study_id = record.get("study_id", "")
            if study_id:
                study_id = study_id.split('-')[-1]

            family_id = record.get("family_id", "")
            if family_id:
                family_id = family_id.split('-')[-1]

            ses_id = record.get("mri_instance", "")

            # Skip if missing required identifiers
            if not study_id:
                self.logger.warning("Skipping record due to missing study_id")
                continue

            # Construct DICOM identifiers
            patient_name = f"cpip-id-{study_id}^fa-{family_id}"
            patient_id = f"sub_{study_id}_ses_{ses_id}_fam_{family_id}"

            # Build entry with mapped fields
            entry = {
                "patient_name": patient_name,
                "patient_id": patient_id,
                "modality": "MR",  # Default modality
                "study_instance_uid": self._generate_instance_uid(),
                "performed_procedure_step_status": "SCHEDULED",
                "data_source": self.get_source_name(),  # Track which data source created this entry
            }

            # Apply field mapping
            for source_field, target_field in field_mapping.items():
                if source_field in record and record[source_field] not in (None, '', 'NaN'):
                    entry[target_field] = record[source_field]

            # Ensure scheduled_start_date/time are populated for generic insertion
            if "scheduled_start_date" not in entry:
                entry["scheduled_start_date"] = record.get("mri_date") or record.get("scheduled_date")
            if "scheduled_start_time" not in entry:
                entry["scheduled_start_time"] = record.get("mri_time") or record.get("scheduled_time")

            entry["scheduled_start_date"] = self._normalize_legacy_date(entry.get("scheduled_start_date"))
            entry["scheduled_start_time"] = self._normalize_legacy_time(entry.get("scheduled_start_time"))

            # Apply protocol name when available
            if "protocol_name" not in entry and self._protocol is not None:
                if isinstance(self._protocol, str):
                    entry["protocol_name"] = self._protocol
                elif self._site_id and isinstance(self._protocol, dict):
                    entry["protocol_name"] = self._protocol.get(self._site_id)

            entries.append(entry)

        return entries

    def _normalize_legacy_date(self, value) -> str | None:
        """Normalize date values to legacy YYYY-MM-DD."""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            value = str(int(value))

        value = str(value).strip()
        if not value:
            return None

        match = re.match(r"^(\d{4})[-/.](\d{2})[-/.](\d{2})$", value)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

        if len(value) == 8 and value.isdigit():
            return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"

        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
        except Exception:
            self.logger.debug(f"Unrecognized date format: {value}")
            return value

    def _normalize_legacy_time(self, value) -> str | None:
        """Normalize time values to legacy HH:MM."""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            value = str(int(value))

        value = str(value).strip()
        if not value:
            return None

        match = re.match(r"^(\d{2}):(\d{2})(?::(\d{2}))?$", value)
        if match:
            hh, mm, _ss = match.groups()
            return f"{hh}:{mm}"

        if len(value) == 6 and value.isdigit():
            return f"{value[0:2]}:{value[2:4]}"

        if len(value) == 4 and value.isdigit():
            return f"{value[0:2]}:{value[2:4]}"

        if len(value) == 2 and value.isdigit():
            return f"{value}:00"

        self.logger.debug(f"Unrecognized time format: {value}")
        return value

    def _generate_instance_uid(self) -> str:
        """Generate a valid Study Instance UID."""
        return f"1.2.840.10008.3.1.2.3.4.{uuid.uuid4().int}"

    def get_source_name(self) -> str:
        """Return source type identifier."""
        return "REDCap"

    def supports_incremental_sync(self) -> bool:
        """REDCap supports incremental sync via date filtering."""
        return True

    def cleanup(self) -> None:
        """Perform memory cleanup after sync."""
        # Force garbage collection
        gc.collect()
        self.logger.debug("REDCap plugin cleanup complete")
