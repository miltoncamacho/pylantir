"""Database upsert helpers shared by data-source sync loops."""

from typing import Any, Dict, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session as OrmSession

from .models import WorklistItem
from .redcap_to_db import generate_instance_uid


WORKLIST_FIELDS = (
    "patient_name",
    "patient_id",
    "patient_birth_date",
    "patient_sex",
    "patient_weight_lb",
    "accession_number",
    "referring_physician_name",
    "modality",
    "study_description",
    "scheduled_station_aetitle",
    "scheduled_start_date",
    "scheduled_start_time",
    "performing_physician",
    "procedure_description",
    "protocol_name",
    "station_name",
    "hisris_coding_designator",
    "performed_procedure_step_status",
)


def _format_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    value_str = str(value).strip()
    if "-" in value_str and len(value_str) >= 10:
        return value_str[:10]
    if len(value_str) == 8 and value_str.isdigit():
        return f"{value_str[0:4]}-{value_str[4:6]}-{value_str[6:8]}"
    return value_str


def _format_time(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    value_str = str(value).strip()
    if ":" in value_str:
        parts = value_str.split(":")
        if len(parts) >= 2:
            return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    if len(value_str) in (4, 6) and value_str.isdigit():
        return f"{value_str[0:2]}:{value_str[2:4]}"
    return value_str


def upsert_worklist_record(
    session: OrmSession,
    record: Dict[str, Any],
    source_name: str,
    protocol: Optional[Dict[str, str]] = None,
    site_id: Optional[str] = None,
) -> Optional[WorklistItem]:
    """Insert or update one source record, preferring its stable source ID."""
    patient_id = record.get("patient_id")
    if not patient_id:
        return None

    source_record_id = record.get("source_record_id")
    if source_record_id is not None:
        source_record_id = str(source_record_id)

    existing = None
    if source_record_id:
        existing = (
            session.query(WorklistItem)
            .filter_by(data_source=source_name, source_record_id=source_record_id)
            .first()
        )

    # Backward-compatible fallback also lets an unchanged legacy row acquire
    # its source_record_id on the first sync after migration.
    if existing is None:
        patient_name = record.get("patient_name")
        query = session.query(WorklistItem).filter_by(patient_id=patient_id)
        query = query.filter(
            or_(WorklistItem.data_source == source_name, WorklistItem.data_source.is_(None))
        )
        if patient_name:
            query = query.filter_by(patient_name=patient_name)
        existing = query.first()

    is_new = existing is None
    item = existing or WorklistItem(study_instance_uid=generate_instance_uid())

    values = dict(record)
    values["scheduled_start_date"] = _format_date(record.get("scheduled_start_date"))
    values["scheduled_start_time"] = _format_time(record.get("scheduled_start_time"))
    values["modality"] = record.get("modality") or "MR"
    values["performed_procedure_step_status"] = (
        record.get("performed_procedure_step_status") or "SCHEDULED"
    )
    if not record.get("protocol_name"):
        values["protocol_name"] = (protocol or {}).get(site_id, "DEFAULT_PROTOCOL")

    for field in WORKLIST_FIELDS:
        # Partial source payloads must not erase fields populated by an earlier
        # sync. New rows naturally leave missing nullable columns as NULL.
        if is_new or field in values:
            setattr(item, field, values.get(field))

    if record.get("study_instance_uid"):
        item.study_instance_uid = record["study_instance_uid"]
    item.data_source = source_name
    item.source_record_id = source_record_id

    if is_new:
        session.add(item)
    return item
