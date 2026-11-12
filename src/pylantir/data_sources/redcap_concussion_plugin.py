"""REDCap data source for the CPIP concussion study."""

from .redcap_plugin import REDCapPlugin


class ConcussionREDCapPlugin(REDCapPlugin):
    """Use the standard REDCap workflow with concussion-study credentials."""

    API_URL_ENV = "REDCAP_API_URL_CONCUSSION"
    API_TOKEN_ENV = "REDCAP_API_TOKEN_CONCUSSION"

    def get_source_name(self) -> str:
        """Return the concussion REDCap source identifier."""
        return "REDCap Concussion"

    def _transform_records(self, raw_records, field_mapping):
        """Normalize concussion identifiers before standard transformation."""
        normalized_records = []
        for record in raw_records:
            normalized_record = dict(record)
            normalized_record["study_id"] = self._strip_prefix(
                record.get("study_id"),
                ("sub_", "sub-"),
            )
            normalized_record["family_id"] = self._strip_prefix(
                record.get("family_id"),
                ("fam_", "fam-"),
            )
            normalized_records.append(normalized_record)

        return super()._transform_records(normalized_records, field_mapping)

    @staticmethod
    def _strip_prefix(value, prefixes):
        normalized = str(value or "").strip()
        lowered = normalized.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix.lower()):
                return normalized[len(prefix):]
        return normalized
