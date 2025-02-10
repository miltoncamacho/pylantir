import os
import logging
from redcap import Project
import uuid
from sqlalchemy.orm import sessionmaker
from .db_setup import engine
from .models import WorklistItem
import time
import threading

lgr = logging.getLogger(__name__)

STOP_EVENT = threading.Event()  # <--- Event used to signal shutdown

# REDCap API Config
REDCAP_API_URL = os.getenv("REDCAP_API_URL", "https://test-redcap.urca.ca/api/")
REDCAP_API_TOKEN = os.getenv("REDCAP_API_TOKEN", "TOKEN")

# Create a session
Session = sessionmaker(bind=engine)



def fetch_redcap_entries(redcap_fields: list) -> list:
    """Fetch scheduled procedures from REDCap using PyCap."""
    project = Project(REDCAP_API_URL, REDCAP_API_TOKEN)

    if not redcap_fields:
        lgr.error("No field mapping (redcap2wl) provided for REDCap retrieval.")
        return []

    # Fetch metadata to get valid REDCap field names
    valid_fields = {field["field_name"] for field in project.export_metadata()}

    # Only keep fields that actually exist in REDCap
    redcap_fields = [field for field in redcap_fields if field in valid_fields]

    if not redcap_fields:
        lgr.error("No valid REDCap fields found in provided mapping.")
        return []

    lgr.info(f"Fetching REDCap data for fields: {redcap_fields}")

    # Fetch records
    records = project.export_records(fields=redcap_fields, format_type="json")

    # Ensure all requested fields exist in every record (fill missing fields with None)
    for record in records:
        record["redcap_event_name"] = record.get("redcap_event_name", "UNKNOWN_EVENT")
        for field in redcap_fields:
            record.setdefault(field, None)  # Fill missing fields with None

    if not records:
        lgr.warning("No records retrieved from REDCap.")

    return records

# TODO: Implement age binning for paricipants
def age_binning():
    return None

def generate_instance_uid():
    """Generate a valid Study Instance UID."""
    return f"1.2.840.10008.3.1.2.3.4.{uuid.uuid4().int}"


def convert_weight(weight, weight_unit):
    """Convert weight to kg if needed."""
    if not weight or not weight_unit:
        return None, None

    weight = float(weight)
    if weight_unit.lower() == "lb":
        return round(weight * 0.453592, 2), weight  # (kg, lb)
    return weight, round(weight / 0.453592, 2)  # (kg, lb)


def mapping_redcap_event_name_to_ses_id(mri_visit_mapping, redcap_event):
    """Map REDCap event name to SES ID."""
    try:
        ses_id = mri_visit_mapping.get(redcap_event, None)
        if ses_id is None:
            raise ValueError(f"SES ID not found for REDCap event: {redcap_event}")
        return ses_id
    except Exception as e:
        lgr.error(f"Error mapping REDCap event name to SES ID: {e}")
        return None


def sync_redcap_to_db(
    mri_visit_mapping: dict,
    site_id: str,
    protocol: dict,
    redcap2wl: dict,
) -> None:
    """Sync REDCap patient data with the worklist database."""

    if not redcap2wl:
        lgr.error("No field mapping (redcap2wl) provided for syncing.")

    session = Session()

    # Extract the REDCap fields that need to be pulled
    default_fields = ["study_id", "family_id", "youth_dob_y", "t1_date", "demo_sex"]
    redcap_fields = list(redcap2wl.keys())

    # Ensure certain default fields are always present
    for i in default_fields:
        if i not in redcap_fields:
            redcap_fields.append(i)

    redcap_entries = fetch_redcap_entries(redcap_fields)

    for record in redcap_entries:
        study_id = record.get("study_id")
        study_id = study_id.split('-')[-1] if study_id else None
        family_id = record.get("family_id")
        family_id = family_id.split('-')[-1] if family_id else None
        ses_id = mapping_redcap_event_name_to_ses_id(
            mri_visit_mapping, record.get("redcap_event_name")
        )

        PatientName = f"cpip-id-{study_id}^fa-{family_id}"
        PatientID = f"sub-{study_id}_ses-{ses_id}_fam-{family_id}_site-{site_id}"

        if not PatientID:
            lgr.warning("Skipping record due to missing Study ID.")
            continue

        patient_weight_kg, patient_weight_lb = convert_weight(
            record.get("weight"), record.get("weight_unit")
        )

        existing_entry = (
            session.query(WorklistItem)
            .filter_by(patient_id=PatientID)
            .first()
        )

        if existing_entry:
            logging.debug(f"Updating existing worklist entry for PatientID {PatientID}")
            existing_entry.patient_name = PatientName
            existing_entry.patient_id = PatientID
            existing_entry.patient_birth_date = record.get("youth_dob_y", "19000101")
            existing_entry.patient_sex = record.get("demo_sex")
            existing_entry.modality = record.get("modality", "MR")

            # Dynamically update DICOM worklist fields from REDCap
            for redcap_field, dicom_field in redcap2wl.items():
                if redcap_field in record:
                    if dicom_field not in default_fields:
                        setattr(existing_entry, dicom_field, record[redcap_field])

            # existing_entry.scheduled_start_date = record.get("scheduled_date")
            # existing_entry.scheduled_start_time = record.get("scheduled_time")
            # existing_entry.protocol_name = record.get("protocol")
            # existing_entry.patient_weight_kg = patient_weight_kg
            # existing_entry.patient_weight_lb = patient_weight_lb
            # existing_entry.referring_physician_name = record.get("referring_physician")
            # existing_entry.performing_physician = record.get("performing_physician")
            # existing_entry.study_description = record.get("study_description")
            # existing_entry.station_name = record.get("station_name")
        else:
            logging.debug(f"Adding new worklist entry for PatientID {PatientID}")
            new_entry = WorklistItem(
                study_instance_uid=generate_instance_uid(),
                patient_name=PatientName,
                patient_id=PatientID,
                patient_birth_date=f"{record.get('youth_dob_y', '2012')}0101",
                patient_sex=record.get("demo_sex"),
                modality=record.get("modality", "MR"),
                # scheduled_start_date=record.get("scheduled_date"),
                # scheduled_start_time=record.get("scheduled_time"),
                protocol_name=protocol.get(site_id, "DEFAULT_PROTOCOL"),
                # patient_weight_kg=patient_weight_kg,
                patient_weight_lb=record.get("patient_weight_lb", ""),
                # referring_physician_name=record.get("referring_physician"),
                # performing_physician=record.get("performing_physician"),
                study_description=record.get("study_description", "CPIP"),
                # station_name=record.get("station_name"),
                performed_procedure_step_status="SCHEDULED"
            )
            session.add(new_entry)

    session.commit()
    session.close()
    logging.info("REDCap data synchronized successfully with DICOM worklist database.")


def sync_redcap_to_db_repeatedly(
    mri_visit_mapping=None,
    site_id=None,
    protocol=None,
    redcap2wl=None,
    interval=60
):
    """
    Keep syncing with REDCap in a loop every `interval` seconds.
    Exit cleanly when STOP_EVENT is set.
    """
    while not STOP_EVENT.is_set():
        try:
            sync_redcap_to_db(
                mri_visit_mapping=mri_visit_mapping,
                site_id=site_id,
                protocol=protocol,
                redcap2wl=redcap2wl,
            )
        except Exception as exc:
            logging.error(f"Error in REDCap sync: {exc}")

        # Wait up to `interval` seconds, or break early if STOP_EVENT is set
        STOP_EVENT.wait(interval)

    logging.info("Exiting sync_redcap_to_db_repeatedly because STOP_EVENT was set.")


if __name__ == "__main__":
    # This block is just a demo usage. In practice, you might set STOP_EVENT
    # from a signal handler or from another part of your code.
    try:
        sync_redcap_to_db_repeatedly(
            mri_visit_mapping=None,
            site_id=None,
            protocol=None,
            redcap2wl=None,
            interval=60
        )
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received. Stopping background sync...")
        STOP_EVENT.set()
