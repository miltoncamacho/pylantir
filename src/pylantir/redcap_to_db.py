import os
import logging
from redcap import Project
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
        "demo_sex"
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

def convert_weight(weight, weight_unit):
    """Convert weight to kg if needed."""
    if not weight or not weight_unit:
        return None, None

    weight = float(weight)
    if weight_unit.lower() == "lb":
        return round(weight * 0.453592, 2), weight  # (kg, lb)
    return weight, round(weight / 0.453592, 2)  # (kg, lb)


def sync_redcap_to_db():
    """Sync REDCap patient data with the worklist database."""
    session = Session()
    redcap_entries = fetch_redcap_entries()

    for record in redcap_entries:
        study_uid = record.get("study_instance_uid")
        if not study_uid:
            logging.warning("Skipping record due to missing StudyInstanceUID")
            continue

        patient_weight_kg, patient_weight_lb = convert_weight(
            record.get("weight"), record.get("weight_unit")
        )

        existing_entry = session.query(WorklistItem).filter_by(study_instance_uid=study_uid).first()

        if existing_entry:
            logging.info(f"Updating existing worklist entry for StudyInstanceUID {study_uid}")
            existing_entry.patient_name = record.get("patient_name")
            existing_entry.patient_id = record.get("patient_id")
            existing_entry.patient_birth_date = record.get("dob")
            existing_entry.patient_sex = record.get("sex")
            existing_entry.modality = record.get("modality")
            existing_entry.scheduled_start_date = record.get("scheduled_date")
            existing_entry.scheduled_start_time = record.get("scheduled_time")
            existing_entry.protocol_name = record.get("protocol")
            existing_entry.patient_weight_kg = patient_weight_kg
            existing_entry.patient_weight_lb = patient_weight_lb
            existing_entry.referring_physician_name = record.get("referring_physician")
            existing_entry.performing_physician = record.get("performing_physician")
            existing_entry.study_description = record.get("study_description")
            existing_entry.station_name = record.get("station_name")
        else:
            logging.info(f"Adding new worklist entry for StudyInstanceUID {study_uid}")
            new_entry = WorklistItem(
                study_instance_uid=study_uid,
                patient_name=record.get("patient_name"),
                patient_id=record.get("patient_id"),
                patient_birth_date=record.get("dob"),
                patient_sex=record.get("sex"),
                modality=record.get("modality"),
                scheduled_start_date=record.get("scheduled_date"),
                scheduled_start_time=record.get("scheduled_time"),
                protocol_name=record.get("protocol"),
                patient_weight_kg=patient_weight_kg,
                patient_weight_lb=patient_weight_lb,
                referring_physician_name=record.get("referring_physician"),
                performing_physician=record.get("performing_physician"),
                study_description=record.get("study_description"),
                station_name=record.get("station_name"),
                performed_procedure_step_status="SCHEDULED"
            )
            session.add(new_entry)

    session.commit()
    session.close()
    logging.info("REDCap data synchronized successfully with DICOM worklist database.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sync_redcap_to_db()
