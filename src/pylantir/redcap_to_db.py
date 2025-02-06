import os
import logging
from redcap import Project
import uuid
from sqlalchemy.orm import sessionmaker
from .db_setup import engine
from .models import WorklistItem

# REDCap API Config
REDCAP_API_URL = os.getenv("REDCAP_API_URL", "https://test-redcap.urca.ca/api/")
REDCAP_API_TOKEN = os.getenv("REDCAP_API_TOKEN", "TOKEN")

# Create a session
Session = sessionmaker(bind=engine)

def fetch_redcap_entries():
    """Fetch scheduled procedures from REDCap using PyCap."""
    project = Project(REDCAP_API_URL, REDCAP_API_TOKEN)

    # Remove 'redcap_event_name' from fields (it is NOT fetch_redcap_entries
    fields = [
        "study_id",
        "family_id",
        "youth_dob_y",
        "t1_date",
        "demo_sex",

    ]

    # Fetch REDCap records (NO export_events argument)
    records = project.export_records(fields=fields, format="json")

    # Extract `redcap_event_name` from each entry if available
    for record in records:
        record["redcap_event_name"] = record.get("redcap_event_name", "UNKNOWN_EVENT")

    if not records:
        logging.warning("No records retrieved from REDCap.")

    return records

# TODO: Implement age binning for paricipants
def age_binning():
    return None

def generate_sop_instance_uid():
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

def mapping_redcap_event_name_to_ses_id(mri_visit_mapping,redcap_event):
    """Map REDCap event name to SES ID."""
    try:
        ses_id = mri_visit_mapping.get(redcap_event, None)
        if ses_id is None:
            raise ValueError(f"SES ID not found for REDCap event: {redcap_event}")
        return ses_id
    except Exception as e:
        logging.error(f"Error mapping REDCap event name to SES ID: {e}")
        return None

def sync_redcap_to_db(mri_visit_mapping=None,site_id=None,protocol=None) -> None:
    """Sync REDCap patient data with the worklist database."""
    session = Session()
    redcap_entries = fetch_redcap_entries()

    for record in redcap_entries:
        study_id = record.get("study_id")
        study_id = record.get("study_id").split('-')[-1] if study_id else None
        family_id = record.get("family_id")
        family_id = record.get("family_id").split('-')[-1] if family_id else None
        site_id = site_id
        ses_id = mapping_redcap_event_name_to_ses_id(mri_visit_mapping, record.get("redcap_event_name"))
        PatientName = f"cpip-id-{study_id}^fa-{family_id}"
        PatientID = f"sub-{study_id}_ses-{ses_id}_fam-{family_id}_site-{site_id}"

        if not study_id:
            logging.warning("Skipping record due to missing Study ID.")
            continue

        patient_weight_kg, patient_weight_lb = convert_weight(
            record.get("weight"), record.get("weight_unit")
        )

        existing_entry = session.query(WorklistItem).filter_by(patient_id=PatientID).first()

        if existing_entry:
            logging.info(f"Updating existing worklist entry for PatientID {PatientID}")
            existing_entry.patient_name = PatientName
            existing_entry.patient_id = PatientID
            existing_entry.patient_birth_date = record.get("youth_dob_y", "19000101")
            existing_entry.patient_sex = record.get("demo_sex")
            existing_entry.modality = record.get("modality", "MR")
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
            logging.info(f"Adding new worklist entry for PatientID {PatientID}")
            new_entry = WorklistItem(
                study_instance_uid=study_uid,
                patient_name=record.get("patient_name"),
                patient_id=record.get("patient_id"),
                patient_birth_date=record.get("youth_dob_y", "19000101"),
                patient_sex=record.get("demo_sex"),
                modality=record.get("modality", "MR"),
                # scheduled_start_date=record.get("scheduled_date"),
                # scheduled_start_time=record.get("scheduled_time"),
                protocol_name=protocol.get(site_id, "DEFAULT_PROTOCOL"),
                # patient_weight_kg=patient_weight_kg,
                # patient_weight_lb=patient_weight_lb,
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sync_redcap_to_db(mri_visit_mapping=None,site_id=None,protocol=None)
