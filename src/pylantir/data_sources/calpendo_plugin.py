"""
Calpendo Data Source Plugin

This module implements the DataSourcePlugin interface for Calpendo WebDAV API integration.
Fetches MRI/EEG scanner bookings from Calpendo and transforms them into DICOM worklist entries.

Version: 1.0.0
Constitutional Compliance:
- Minimalist Dependencies: requests (HTTP client), pytz (timezone handling)
- Healthcare Data Integrity: Full audit trail, change detection via hashing
- Operational Observability: Structured logging at all levels
"""

import os
import logging
import re
import hashlib
import json
from urllib.parse import quote
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
import requests
import pytz
import gc

from .base import DataSourcePlugin, PluginFetchError, PluginConfigError

lgr = logging.getLogger(__name__)


class CalendoPlugin(DataSourcePlugin):
    """
    Calpendo data source plugin.

    Connects to Calpendo WebDAV API and fetches scanner booking entries with
    regex-based field extraction, timezone conversion, and change detection.

    Configuration Requirements:
        - base_url: Calpendo server URL
        - resources: List of resource names to sync (e.g., ["3T Diagnostic", "EEG"])
        - field_mapping: Dict mapping Calpendo fields to WorklistItem fields

    Environment Variables:
        - CALPENDO_USERNAME: Calpendo API username
        - CALPENDO_PASSWORD: Calpendo API password
    """

    # Status mapping: Calpendo status → DICOM procedure step status
    STATUS_MAPPING = {
        "Approved": "SCHEDULED",
        "In Progress": "IN_PROGRESS",
        "Completed": "COMPLETED",
        "Cancelled": "DISCONTINUED",
        "Pending": "SCHEDULED",
    }

    def __init__(self):
        super().__init__()
        self._base_url = None
        self._username = None
        self._password = None
        self._config = None
        self._timezone = None

    def validate_config(self, config: Dict) -> Tuple[bool, str]:
        """
        Validate Calpendo plugin configuration.

        Checks required fields, environment variables, and field_mapping structure.
        """
        # Store config for later use
        self._config = config

        # Check required config fields
        if "base_url" not in config:
            return (False, "Missing required configuration key: base_url")

        if "resources" not in config:
            return (False, "Missing required configuration key: resources")

        if not isinstance(config["resources"], list) or len(config["resources"]) == 0:
            return (False, "resources must be a non-empty list")

        if "field_mapping" not in config:
            return (False, "Missing required configuration key: field_mapping")

        # Check environment variables
        self._username = os.getenv("CALPENDO_USERNAME")
        self._password = os.getenv("CALPENDO_PASSWORD")

        if not self._username or not self._password:
            return (False, "CALPENDO_USERNAME and CALPENDO_PASSWORD environment variables must be set")

        self._base_url = config["base_url"]

        # Validate optional fields
        lookback_multiplier = config.get("lookback_multiplier", 2)
        if not isinstance(lookback_multiplier, (int, float)) or lookback_multiplier <= 0:
            return (False, "lookback_multiplier must be a positive number")

        allowed_studies = config.get("allowed_studies")
        if allowed_studies is not None:
            if not isinstance(allowed_studies, list) or not all(
                isinstance(item, str) and item.strip() for item in allowed_studies
            ):
                return (False, "allowed_studies must be a non-empty list of strings")
            config["allowed_studies"] = [item.strip() for item in allowed_studies if item.strip()]
            if not config["allowed_studies"]:
                return (False, "allowed_studies must be a non-empty list of strings")

        # Validate timezone
        timezone_str = config.get("timezone", "America/Edmonton")
        try:
            self._timezone = pytz.timezone(timezone_str)
        except Exception as e:
            return (False, f"Invalid timezone '{timezone_str}': {e}")

        # Validate field_mapping structure
        field_mapping = config.get("field_mapping", {})
        for target_field, mapping in field_mapping.items():
            if isinstance(mapping, dict) and "_extract" in mapping:
                extract_config = mapping["_extract"]
                if "pattern" not in extract_config:
                    return (False, f"Field '{target_field}' has _extract but missing 'pattern' key")

        self.logger.debug(f"Calpendo plugin validated: {len(config['resources'])} resources")
        return (True, "")

    def fetch_entries(
        self,
        field_mapping: Dict[str, str],
        interval: float
    ) -> List[Dict]:
        """
        Fetch worklist entries from Calpendo.

        Uses rolling window sync strategy to fetch bookings modified within
        the lookback period, applies change detection to minimize DB writes.
        """
        try:
            # Validate field mapping presence
            if not field_mapping:
                field_mapping = self._config.get("field_mapping", {}) if self._config else {}
                self.logger.warning(
                    "No field_mapping provided to Calpendo plugin. "
                    "config_field_mapping_keys=%s",
                    list(field_mapping.keys()),
                )
            else:
                self.logger.debug(
                    "Calpendo field_mapping keys: %s",
                    list(field_mapping.keys()),
                )

            # Calculate rolling window
            now = datetime.now(self._timezone)
            window_mode = self._config.get("window_mode")
            use_daily_window = self._config.get("daily_window", False)

            if window_mode == "today" or use_daily_window:
                start_time = self._timezone.localize(
                    datetime(now.year, now.month, now.day)
                )
                end_time = start_time + timedelta(days=1)
                self.logger.debug(
                    "Using daily window from %s to %s",
                    start_time.isoformat(),
                    end_time.isoformat(),
                )
            else:
                lookback_multiplier = self._config.get("lookback_multiplier", 2)
                start_time = now - timedelta(seconds=interval * lookback_multiplier)
                end_time = now + timedelta(hours=24)

            self.logger.debug(
                f"Fetching Calpendo bookings from {start_time.isoformat()} "
                f"to {end_time.isoformat()}"
            )

            # Fetch booking IDs in window
            booking_ids = self._fetch_bookings_in_window(start_time, end_time)
            self.logger.debug(
                "Found %s bookings in window (%s to %s)",
                len(booking_ids),
                start_time.isoformat(),
                end_time.isoformat(),
            )

            if not booking_ids:
                return []

            # Fetch details in parallel
            bookings = self._fetch_booking_details_parallel(booking_ids)

            # Transform and filter
            entries = []
            for booking in bookings:
                entry = self._transform_booking_to_entry(booking, field_mapping)
                if entry:  # Skip invalid bookings
                    entries.append(entry)

            self.logger.debug(f"Transformed {len(entries)} valid worklist entries")

            # Clean up
            gc.collect()

            return entries

        except Exception as e:
            self.logger.error(f"Failed to fetch Calpendo entries: {e}")
            raise PluginFetchError(f"Calpendo fetch failed: {e}") from e

    def _build_booking_query(self, start_time: datetime, end_time: datetime) -> str:
        """
        Construct Calpendo WebDAV query string.

        Query format: AND/OR logic with date ranges and filters
        """
        # Format dates as YYYYMMDD-HHMM
        start_str = start_time.strftime("%Y%m%d-%H%M")
        end_str = end_time.strftime("%Y%m%d-%H%M")

        # Base date range (AND) — matches example_for_calpendo.py behavior
        query = f"AND/dateRange.start/GE/{start_str}/dateRange.start/LT/{end_str}"

        # Resource filter (OR) — URL-encode resource names
        resources = self._config.get("resources", [])
        if resources:
            resource_filters = "/OR" + "".join([
                f"/resource.name/EQ/{quote(r)}" for r in resources
            ])
            query += resource_filters

        # Status filter (AND)
        status_filter = self._config.get("status_filter")
        if status_filter:
            query += f"/status/EQ/{quote(status_filter)}"

        self.logger.debug(f"Built query: {query}")
        return query

    def _fetch_bookings_in_window(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[int]:
        """Query Calpendo for booking IDs in time window."""
        query = self._build_booking_query(start_time, end_time)
        url = f"{self._base_url}/webdav/q/Calpendo.Booking/{query}"

        auth = (self._username, self._password)

        try:
            self.logger.debug(f"Fetching bookings from: {url}")
            response = requests.get(url, auth=auth, timeout=30)
            response.raise_for_status()
            self.logger.debug(
                "Calpendo booking list response OK (status %s)",
                response.status_code,
            )

            data = response.json()
            booking_ids = [b["id"] for b in data.get("biskits", [])]

            self.logger.debug(f"Fetched {len(booking_ids)} booking IDs")
            return booking_ids

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise PluginFetchError("Calpendo authentication failed") from e
            raise PluginFetchError(f"HTTP error fetching bookings: {e}") from e
        except Exception as e:
            raise PluginFetchError(f"Failed to fetch bookings: {e}") from e

    def _fetch_booking_details(self, booking_id: int) -> Optional[Dict]:
        """Fetch detailed booking information."""
        url = f"{self._base_url}/webdav/b/Calpendo.Booking/{booking_id}"
        auth = (self._username, self._password)

        try:
            response = requests.get(url, auth=auth, timeout=10)
            if response.status_code == 404:
                self.logger.warning(f"Booking {booking_id} not found (deleted?)")
                return None
            response.raise_for_status()
            self.logger.debug(
                "Calpendo booking detail response OK (status %s) for booking %s",
                response.status_code,
                booking_id,
            )

            booking = response.json()

            properties = booking.get("properties") if isinstance(booking.get("properties"), dict) else {}
            self.logger.debug(
                "Calpendo booking payload summary for %s: biskitType=%s keys=%s properties_keys=%s title=%s properties.title=%s formattedName=%s dateRange=%s status=%s",
                booking_id,
                booking.get("biskitType"),
                list(booking.keys()),
                list(properties.keys()) if isinstance(properties, dict) else None,
                booking.get("title"),
                properties.get("title") if isinstance(properties, dict) else None,
                booking.get("formattedName"),
                properties.get("dateRange") if isinstance(properties, dict) else None,
                properties.get("status") if isinstance(properties, dict) else booking.get("status"),
            )

            # Fetch operator for MRIScan
            if booking.get("biskitType") == "MRIScan":
                operator = self._fetch_mri_operator(booking_id)
                if operator:
                    booking["operator"] = operator

            return booking

        except requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP error fetching booking {booking_id}: {e}")
            raise PluginFetchError(f"Booking detail fetch failed: {e}") from e
        except Exception as e:
            self.logger.error(f"Failed to fetch booking {booking_id}: {e}")
            return None

    def _fetch_mri_operator(self, booking_id: int) -> Optional[str]:
        """Retrieve operator name for MRIScan bookings."""
        url = f"{self._base_url}/webdav/q/MRIScan/id/eq/{booking_id}?paths=Operator.name"
        auth = (self._username, self._password)

        try:
            response = requests.get(url, auth=auth, timeout=10)
            response.raise_for_status()
            self.logger.debug(
                "Calpendo MRI operator response OK (status %s) for booking %s",
                response.status_code,
                booking_id,
            )

            data = response.json()
            biskits = data.get("biskits", [])
            if biskits and len(biskits) > 0:
                operator_data = biskits[0].get("properties", {}).get("Operator", {})
                return operator_data.get("name")

            return None

        except Exception as e:
            self.logger.warning(f"Failed to fetch operator for booking {booking_id}: {e}")
            return None

    def _fetch_booking_details_parallel(self, booking_ids: List[int]) -> List[Dict]:
        """Fetch booking details in parallel using ThreadPoolExecutor."""
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(self._fetch_booking_details, booking_ids))

        # Filter out None (deleted bookings)
        bookings = [b for b in results if b is not None]

        self.logger.debug(f"Fetched {len(bookings)}/{len(booking_ids)} booking details")
        return bookings

    def _extract_field_with_regex(self, source_value: str, extract_config: Dict) -> str:
        """
        Apply regex pattern to extract field value.

        Falls back to original value if pattern doesn't match.
        """
        if not source_value:
            return ""

        pattern_str = extract_config.get("pattern")
        group_num = extract_config.get("group", 0)

        try:
            pattern = re.compile(pattern_str)
            match = pattern.match(source_value)

            if match:
                return match.group(group_num)
            else:
                self.logger.warning(
                    f"Regex pattern '{pattern_str}' no match for '{source_value}', "
                    f"using original value"
                )
                return source_value

        except Exception as e:
            raise PluginConfigError(f"Invalid regex pattern '{pattern_str}': {e}") from e

    def _parse_formatted_name_dates(self, formatted_name: str) -> Tuple[datetime, datetime]:
        """
        Extract start/end times from formattedName field.

        Format: "[2026-01-27 14:00:00.0, 2026-01-27 15:30:00.0]"
        """
        pattern = r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+), (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]"
        match = re.match(pattern, formatted_name)

        if not match:
            raise ValueError(f"Invalid formattedName format: {formatted_name}")

        start_str, end_str = match.groups()
        start_naive = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S.%f")
        end_naive = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S.%f")

        # Localize to configured timezone
        start_dt = self._timezone.localize(start_naive)
        end_dt = self._timezone.localize(end_naive)

        return start_dt, end_dt

    def _convert_to_utc(self, dt: datetime) -> datetime:
        """Convert timezone-aware datetime to UTC."""
        return dt.astimezone(pytz.UTC)

    def _map_status_to_dicom(self, calpendo_status: str) -> str:
        """Map Calpendo status to DICOM procedure step status."""
        return self.STATUS_MAPPING.get(calpendo_status, "SCHEDULED")

    def _map_resource_to_modality(self, resource_name: str) -> str:
        """
        Map resource name to modality code.

        Supports exact and prefix matching from config.
        """
        mapping = self._config.get("resource_modality_mapping", {})

        # Exact match
        if resource_name in mapping:
            return mapping[resource_name]

        # Prefix match
        for prefix, modality in mapping.items():
            if resource_name.startswith(prefix):
                return modality

        # Default to resource name
        return resource_name

    def _get_nested_value(self, data: Dict, key_path: str) -> Optional[str]:
        """
        Extract nested value from dict using dot notation.

        Example: "properties.project.formattedName" → data["properties"]["project"]["formattedName"]
        """
        keys = key_path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return None
            else:
                return None

        if value is None and len(keys) == 1 and isinstance(data, dict):
            properties = data.get("properties")
            if isinstance(properties, dict) and key_path in properties:
                value = properties.get(key_path)

        return str(value) if value is not None else None

    def _parse_date_range_dates(self, date_range: Dict) -> Optional[Tuple[datetime, datetime]]:
        """Parse dateRange.start/end into timezone-aware datetimes."""
        if not isinstance(date_range, dict):
            return None

        start_str = date_range.get("start")
        end_str = date_range.get("end") or date_range.get("finish")

        if not start_str or not end_str:
            return None

        def _parse_iso(value: str) -> Optional[datetime]:
            try:
                normalized = value.replace("Z", "+00:00")
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = self._timezone.localize(dt)
                return dt
            except Exception:
                return None

        start_dt = _parse_iso(start_str)
        end_dt = _parse_iso(end_str)

        if start_dt and end_dt:
            return (start_dt, end_dt)
        return None

    def _transform_booking_to_entry(
        self,
        booking: Dict,
        field_mapping: Dict[str, str]
    ) -> Optional[Dict]:
        """
        Transform Calpendo booking to worklist entry.

        Applies field mappings, regex extraction, timezone conversion,
        and status/resource mapping.
        """
        entry = {}

        # Apply field mappings
        for target_field, mapping_config in field_mapping.items():
            source_value = None

            if isinstance(mapping_config, dict):
                # Complex mapping with extraction
                source_key = mapping_config.get("source_field")
                if source_key:
                    source_value = self._get_nested_value(booking, source_key)
                    self.logger.debug(
                        "Calpendo mapping: target=%s source=%s raw_value=%s",
                        target_field,
                        source_key,
                        source_value,
                    )

                # Apply regex extraction if configured
                if source_value and "_extract" in mapping_config:
                    source_value = self._extract_field_with_regex(
                        source_value, mapping_config["_extract"]
                    )
                    self.logger.debug(
                        "Calpendo extraction: target=%s extracted_value=%s",
                        target_field,
                        source_value,
                    )
            else:
                # Simple string mapping
                source_value = self._get_nested_value(booking, mapping_config)
                self.logger.debug(
                    "Calpendo mapping: target=%s source=%s raw_value=%s",
                    target_field,
                    mapping_config,
                    source_value,
                )

            entry[target_field] = source_value

        # Fallback to properties.title if patient_id/patient_name still missing
        properties_title = None
        if isinstance(booking.get("properties"), dict):
            properties_title = booking.get("properties", {}).get("title")

        booking_title = booking.get("title")

        if properties_title is not None and not str(properties_title).strip():
            properties_title = None
        if booking_title is not None and not str(booking_title).strip():
            booking_title = None

        if not entry.get("patient_id"):
            entry["patient_id"] = properties_title or booking_title

        if not entry.get("patient_name"):
            entry["patient_name"] = properties_title or booking_title

        allowed_studies = self._config.get("allowed_studies") if self._config else None
        if allowed_studies:
            study_description = entry.get("study_description")
            normalized_description = study_description.strip() if isinstance(study_description, str) else None
            if not normalized_description or normalized_description not in allowed_studies:
                self.logger.info(
                    "Skipping booking %s: study_description not allowed (value=%s allowed=%s)",
                    booking.get("id"),
                    study_description,
                    allowed_studies,
                )
                return None

        # Extract and convert date/time from formattedName
        formatted_name = booking.get("formattedName")
        if formatted_name:
            try:
                start_dt, end_dt = self._parse_formatted_name_dates(formatted_name)
                start_utc = self._convert_to_utc(start_dt)
                end_utc = self._convert_to_utc(end_dt)

                entry["scheduled_start_date"] = start_utc.date()
                entry["scheduled_start_time"] = start_utc.time()

                # Calculate duration in minutes
                duration = (end_utc - start_utc).total_seconds() / 60
                entry["scheduled_procedure_step_duration"] = int(duration)

            except Exception as e:
                self.logger.warning(
                    f"Failed to parse formattedName for booking {booking.get('id')}: {e}"
                )
        else:
            date_range = self._get_nested_value(booking, "properties.dateRange")
            parsed = self._parse_date_range_dates(booking.get("properties", {}).get("dateRange"))
            if parsed:
                start_dt, end_dt = parsed
                self.logger.debug(
                    "Calpendo dateRange parsed: booking_id=%s start=%s end=%s",
                    booking.get("id"),
                    start_dt,
                    end_dt,
                )
                start_utc = self._convert_to_utc(start_dt)
                end_utc = self._convert_to_utc(end_dt)

                entry["scheduled_start_date"] = start_utc.date()
                entry["scheduled_start_time"] = start_utc.time()

                duration = (end_utc - start_utc).total_seconds() / 60
                entry["scheduled_procedure_step_duration"] = int(duration)
            else:
                self.logger.warning(
                    "Booking %s missing formattedName and parsable dateRange; dateRange=%s",
                    booking.get("id"),
                    date_range,
                )

        # Map status
        status_value = booking.get("status") or self._get_nested_value(booking, "properties.status")
        if status_value:
            entry["performed_procedure_step_status"] = self._map_status_to_dicom(
                status_value
            )

        # Map resource to modality
        resource_name = self._get_nested_value(booking, "properties.resource.formattedName")
        if resource_name:
            entry["modality"] = self._map_resource_to_modality(resource_name)

        # Track data source
        entry["data_source"] = self.get_source_name()

        # Add booking hash for change detection
        booking_hash = self._compute_booking_hash(booking)
        entry["notes"] = json.dumps({"booking_hash": booking_hash})

        # Validate required fields
        required = ["patient_id", "scheduled_start_date", "scheduled_start_time"]
        for field in required:
            if not entry.get(field):
                booking_id = booking.get("id")
                if field == "patient_id":
                    title_value = booking.get("title")
                    properties_title_value = None
                    if isinstance(booking.get("properties"), dict):
                        properties_title_value = booking.get("properties", {}).get("title")
                    if not title_value:
                        title_value = properties_title_value
                    mapping_config = field_mapping.get("patient_id")
                    self.logger.warning(
                        "Booking %s missing required field '%s', skipping. "
                        "title=%s properties_title=%s mapping=%s extracted_patient_id=%s extracted_patient_name=%s "
                        "field_mapping_keys=%s booking_keys=%s properties_keys=%s biskitType=%s",
                        booking_id,
                        field,
                        title_value,
                        properties_title_value,
                        mapping_config,
                        entry.get("patient_id"),
                        entry.get("patient_name"),
                        list(field_mapping.keys()),
                        list(booking.keys()),
                        list(booking.get("properties", {}).keys()) if isinstance(booking.get("properties"), dict) else None,
                        booking.get("biskitType"),
                    )
                else:
                    self.logger.warning(
                        "Booking %s missing required field '%s', skipping",
                        booking_id,
                        field,
                    )
                return None

        return entry

    def _compute_booking_hash(self, booking: Dict) -> str:
        """
        Compute SHA256 hash of critical booking fields for change detection.
        """
        critical_fields = {
            "title": booking.get("title", ""),
            "status": booking.get("status", ""),
            "formattedName": booking.get("formattedName", ""),
            "project": self._get_nested_value(booking, "properties.project.formattedName") or "",
            "resource": self._get_nested_value(booking, "properties.resource.formattedName") or "",
        }

        json_str = json.dumps(critical_fields, sort_keys=True)
        hash_hex = hashlib.sha256(json_str.encode()).hexdigest()
        return hash_hex

    def get_source_name(self) -> str:
        """Return human-readable source type identifier."""
        return "Calpendo"

    def supports_incremental_sync(self) -> bool:
        """Calpendo plugin supports incremental sync via rolling window."""
        return True

    def cleanup(self) -> None:
        """Perform cleanup after sync."""
        gc.collect()
