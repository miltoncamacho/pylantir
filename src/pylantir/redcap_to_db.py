import os
import logging
import pandas as pd
from redcap import Project
import uuid
from sqlalchemy.orm import sessionmaker
from .db_setup import engine
from .models import WorklistItem
import time
import threading
from datetime import datetime, time, date, timedelta
import gc

lgr = logging.getLogger(__name__)

# Optional memory monitoring (install with: pip install psutil)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    lgr.debug("psutil not available. Memory monitoring will be limited.")

STOP_EVENT = threading.Event()  # <--- Event used to signal shutdown

# REDCap API Config
REDCAP_API_URL = os.getenv("REDCAP_API_URL", "https://test-redcap.urca.ca/api/")
REDCAP_API_TOKEN = os.getenv("REDCAP_API_TOKEN", "TOKEN")

# Create a session
Session = sessionmaker(bind=engine)



def fetch_redcap_entries(redcap_fields: list, interval: float) -> list:
    """Fetch REDCap entries using PyCap and return a list of filtered dicts."""
    project = Project(REDCAP_API_URL, REDCAP_API_TOKEN)

    if not redcap_fields:
        lgr.error("No field mapping (redcap2wl) provided for REDCap retrieval.")
        return []

    # Fetch metadata to get valid REDCap field names
    valid_fields = {field["field_name"] for field in project.export_metadata()}
    redcap_fields = [field for field in redcap_fields if field in valid_fields]

    if not redcap_fields:
        lgr.error("No valid REDCap fields found in provided mapping.")
        return []

    lgr.info(f"Fetching REDCap data for fields: {redcap_fields}")

    # Export data
    datetime_now = datetime.now()
    datetime_interval = datetime_now - timedelta(seconds=interval)
    records = project.export_records(fields=redcap_fields, date_begin=datetime_interval, date_end=datetime_now, format_type="df")

    # Clean up PyCap Project immediately after export to free API client cache
    del project
    gc.collect()

    if records.empty:
        lgr.warning("No records retrieved from REDCap.")
        # Explicitly clean up the empty DataFrame to release any allocated buffers
        del records
        gc.collect()
        return []

    filtered_records = []

    # Group by 'record_id' (index level 0)
    # Convert to list to avoid holding groupby iterator reference
    record_groups = list(records.groupby(level=0))
    for record_id, group in record_groups:

        # Try to get baseline (non-repeated instrument) values
        baseline_rows = group[group['redcap_repeat_instrument'].isna()]
        baseline_row = baseline_rows.iloc[0] if not baseline_rows.empty else {}

        # Filter for valid MRI rows only
        mri_rows = group[
            (group["redcap_repeat_instrument"] == "mri") &
            (group.get("mri_instance").notna()) &
            (group.get("mri_instance") != "" ) &
            (group.get("mri_date").notna()) &
            (group.get("mri_time").notna())
        ]

        for _, mri_row in mri_rows.iterrows():
            record = {"record_id": record_id}

            # Merge fields from baseline and mri_row, only include requested fields
            for field in redcap_fields:
                record[field] = (
                    mri_row.get(field)
                    if pd.notna(mri_row.get(field))
                    else baseline_row.get(field)
                )

            filtered_records.append(record)

    # Explicitly clean up DataFrame and groupby list to free memory
    del record_groups
    del records
    gc.collect()
    
    return filtered_records

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


def get_memory_usage():
    """Get current memory usage statistics."""
    if PSUTIL_AVAILABLE:
        process = psutil.Process()
        memory_info = process.memory_info()
        return {
            'rss_mb': round(memory_info.rss / 1024 / 1024, 2),
            'vms_mb': round(memory_info.vms / 1024 / 1024, 2),
            'percent': round(process.memory_percent(), 2)
        }
    else:
        # Fallback to basic resource usage
        import resource
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            # maxrss is in KB on Linux, bytes on macOS
            import platform
            if platform.system() == 'Darwin':  # macOS
                maxrss_mb = round(usage.ru_maxrss / 1024 / 1024, 2)
            else:  # Linux and others
                maxrss_mb = round(usage.ru_maxrss / 1024, 2)
            return {
                'max_rss_mb': maxrss_mb,
                'user_time': round(usage.ru_utime, 2),
                'system_time': round(usage.ru_stime, 2)
            }
        except Exception as e:
            lgr.warning(f"Could not get memory usage: {e}")
            return {}


def cleanup_memory_and_connections():
    """
    Comprehensive cleanup function to manage memory and database connections.
    This function should be called after each synchronization cycle.
    """
    lgr.debug("Starting memory and connection cleanup...")
    
    # Get memory usage before cleanup
    memory_before = get_memory_usage()
    
    try:
        # 1. Clear pandas cache and temporary objects
        # Force garbage collection of pandas objects
        gc.collect()
        
        # 2. Close any idle database connections in the pool
        if hasattr(engine, 'pool'):
            # Dispose of the connection pool to free up connections
            lgr.debug("Disposing database connection pool")
            engine.pool.dispose()
        
        # 3. Force Python garbage collection targeting all generations
        # Target generation 2 (oldest) first to catch long-lived objects
        collected = gc.collect(generation=2)  # Oldest generation
        collected += gc.collect(generation=1)  # Middle generation
        collected += gc.collect(generation=0)  # Youngest generation
        
        # 4. Clear any cached SQLAlchemy metadata
        if hasattr(engine, 'pool'):
            # Recreate the pool with fresh connections
            engine.pool.recreate()
        
        # Get memory usage after cleanup
        memory_after = get_memory_usage()
        
        # Log cleanup results with simplified, focused metrics
        if memory_before and memory_after and 'rss_mb' in memory_before:
            freed = memory_before['rss_mb'] - memory_after['rss_mb']
            lgr.info(
                f"Memory cleanup: Before={memory_before['rss_mb']:.1f}MB, "
                f"After={memory_after['rss_mb']:.1f}MB, "
                f"Freed={freed:.1f}MB, "
                f"Objects={collected}"
            )
        else:
            lgr.info(f"Memory cleanup: Collected {collected} objects")
            
    except Exception as e:
        lgr.error(f"Error during cleanup: {e}")
        # Don't let cleanup errors stop the main process
        pass


def sync_redcap_to_db(
    site_id: str,
    protocol: dict,
    redcap2wl: dict,
    interval: float = 60.0,
) -> None:
    """Sync REDCap patient data with the worklist database."""

    if not redcap2wl:
        lgr.error("No field mapping (redcap2wl) provided for syncing.")
        return

    # Log memory usage before sync
    memory_before = get_memory_usage()
    if memory_before:
        lgr.debug(f"Memory before sync: {memory_before}")

    session = None
    try:
        session = Session()

        #TODO: Implement the repeat visit mapping
        # Extract the REDCap fields that need to be pulled
        default_fields = ["record_id", "study_id", "redcap_repeat_instrument", "mri_instance", "mri_date", "mri_time", "family_id", "youth_dob_y", "t1_date", "demo_sex"]
        redcap_fields = list(redcap2wl.keys())

        # Ensure certain default fields are always present
        for i in default_fields:
            if i not in redcap_fields:
                redcap_fields.append(i)

        redcap_entries = fetch_redcap_entries(redcap_fields, interval)

        for record in redcap_entries:
            study_id = record.get("study_id")
            study_id = study_id.split('-')[-1] if study_id else None
            family_id = record.get("family_id")
            family_id = family_id.split('-')[-1] if family_id else None
            repeat_id = record.get("redcap_repeat_instance") if record.get("redcap_repeat_instance") != "" else "1" # Default to 1 if not set
            lgr.debug(f"Processing record for Study ID: {study_id} and Family ID: {family_id}")
            lgr.debug(f"This is the repeat event {repeat_id}")
            ses_id = record.get("mri_instance")

            PatientName = f"cpip-id-{study_id}^fa-{family_id}"
            PatientID = f"sub_{study_id}_ses_{ses_id}_fam_{family_id}_site_{site_id}"
            PatientID_ = f"sub-{study_id}_ses-{ses_id}_fam-{family_id}_site-{site_id}"

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

            existing_entry_ = (
                session.query(WorklistItem)
                .filter_by(patient_id=PatientID_)
                .first()
            )
            if existing_entry:
                logging.debug(f"Updating existing worklist entry for PatientID {PatientID}")
            elif existing_entry_:
                logging.debug(f"Updating existing worklist entry for PatientID {PatientID_}")
                existing_entry = existing_entry_

            if existing_entry:
                existing_entry.patient_name = PatientName
                existing_entry.patient_id = PatientID
                existing_entry.patient_birth_date = record.get("youth_dob_y", "19000101")
                existing_entry.patient_sex = record.get("demo_sex")
                existing_entry.modality = record.get("modality", "MR")
                existing_entry.scheduled_start_date = record.get("mri_date")
                existing_entry.scheduled_start_time = record.get("mri_time")
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
                logging.info(f"Adding new worklist entry for PatientID {PatientID} scheduled for {record.get('mri_date')} at {record.get('mri_time')}")
                new_entry = WorklistItem(
                    study_instance_uid=generate_instance_uid(),
                    patient_name=PatientName,
                    patient_id=PatientID,
                    patient_birth_date=f"{record.get('youth_dob_y', '2012')}0101",
                    patient_sex=record.get("demo_sex"),
                    modality=record.get("modality", "MR"),
                    scheduled_start_date=record.get("mri_date"),
                    scheduled_start_time=record.get("mri_time"),
                    protocol_name=protocol.get(site_id, "DEFAULT_PROTOCOL"),
                    hisris_coding_designator=protocol.get("mapping", "scannermapper"),
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
        logging.info("REDCap data synchronized successfully with DICOM worklist database.")
        
    except Exception as e:
        lgr.error(f"Error during REDCap synchronization: {e}")
        if session:
            session.rollback()
        raise  # Re-raise to let calling code handle it
    finally:
        # Always ensure session is properly closed
        if session:
            # Detach all ORM objects from session to clear identity map
            session.expunge_all()
            session.close()
        
        # Perform cleanup after sync
        cleanup_memory_and_connections()
        
        # Log memory usage after cleanup
        memory_after = get_memory_usage()
        if memory_after:
            lgr.debug(f"Memory after sync and cleanup: {memory_after}")


def sync_redcap_to_db_repeatedly(
    site_id=None,
    protocol=None,
    redcap2wl=None,
    interval=60,
    operation_interval={"start_time": [00,00], "end_time": [23,59]},
):
    """
    Keep syncing with REDCap in a loop every `interval` seconds,
    but only between operation_interval[start_time] and operation_interval[end_time].
    Exit cleanly when STOP_EVENT is set.
    """
    if operation_interval is None:
        operation_interval = {"start_time": [0, 0], "end_time": [23, 59]}

    start_h, start_m = operation_interval.get("start_time", [0, 0])
    end_h, end_m = operation_interval.get("end_time", [23, 59])
    start_time = time(start_h, start_m)
    end_time = time(end_h, end_m)

    # last_sync_date = datetime.now().date()
    last_sync_date = datetime.now().date() - timedelta(days=1)
    interval_sync = interval + 300 # add 5 minutes to the interval to overlap with the previous sync and avoid missing data

    while not STOP_EVENT.is_set():
        # === 1) BASELINE: set defaults for flags and wait-time each iteration ===
        is_first_run = False
        extended_interval = interval

        # === 2) FIGURE OUT "NOW" in hours/minutes (zero out seconds) ===
        now_dt = datetime.now().replace(second=0, microsecond=0)
        now_time = now_dt.time()
        today_date = now_dt.date()

        # === 3) ONLY SYNC IF WE'RE WITHIN [start_time, end_time] ===
        if start_time <= now_time <= end_time:
            # Check if we haven't synced today yet
            is_first_run = (last_sync_date != today_date)

            # If it really *is* the first sync of this new day (and it's not the very first run ever)
            if is_first_run and (last_sync_date is not None):
                logging.info(f"First sync of the day for site {site_id} at {now_time}.")
                # Calculate how many seconds from "end_time of yesterday" until "start_time of today"
                yesterday = last_sync_date
                dt_end_yesterday = datetime.combine(yesterday, end_time)
                dt_start_today = datetime.combine(today_date, start_time)
                delta = dt_start_today - dt_end_yesterday
                # guaranteed to be positive if yesterday < today
                extended_interval = delta.total_seconds()
                logging.info(f"Using extended interval: {extended_interval}, {interval} seconds until next sync.")
            else:
                # Either not first run, or last_sync_date is None (this is first-ever run)
                logging.info(f"Using default interval {interval} seconds.")

            # --- CALL THE SYNC FUNCTION INSIDE A TRY/EXCEPT ---
            logging.debug(f"Syncing REDCap to DB for site {site_id} at {now_time}.")
            logging.debug(f"First run {is_first_run}")
            try:
                logging.debug(f"last_sync_date was: {last_sync_date}")
                if is_first_run and (last_sync_date is not None):
                    sync_redcap_to_db(
                        site_id=site_id,
                        protocol=protocol,
                        redcap2wl=redcap2wl,
                        interval=extended_interval,
                    )
                else:
                    sync_redcap_to_db(
                        site_id=site_id,
                        protocol=protocol,
                        redcap2wl=redcap2wl,
                        interval=interval_sync,
                    )
                last_sync_date = today_date
                logging.debug(f"REDCap sync completed at {now_time}. Next sync atempt in {interval} seconds.")
            except Exception as exc:
                logging.error(f"Error in REDCap sync: {exc}")
                # Run cleanup even after errors to prevent memory buildup
                try:
                    cleanup_memory_and_connections()
                except Exception as cleanup_exc:
                    logging.warning(f"Cleanup failed after sync error: {cleanup_exc}")
        else:
            # We're outside of operation hours. Just log once and sleep a bit.
            logging.debug(
                f"Current time {now_time} is outside operation window "
                f"({start_time}–{end_time}). Sleeping for {interval} seconds."
            )
            
            # Run periodic cleanup even during off-hours to prevent memory buildup
            # Only run every 10th cycle to avoid excessive overhead
            if (now_dt.hour == 3 and now_dt.minute == 0):  # Daily cleanup at 3 AM
                try:
                    logging.info("Running scheduled memory cleanup during off-hours")
                    cleanup_memory_and_connections()
                except Exception as cleanup_exc:
                    logging.warning(f"Off-hours cleanup failed: {cleanup_exc}")

        # === 4) WAIT before the next iteration. We already set extended_interval above. ===
        logging.debug(f"Sleeping for {interval} seconds before next check...")
        STOP_EVENT.wait(interval)

    logging.info("Exiting sync_redcap_to_db_repeatedly because STOP_EVENT was set.")


if __name__ == "__main__":
    try:
        sync_redcap_to_db_repeatedly(
            site_id=None,
            protocol=None,
            redcap2wl=None,
            interval=60,
            operation_interval={"start_time": [0, 0], "end_time": [23, 59]},
        )
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received. Stopping background sync...")
        STOP_EVENT.set()