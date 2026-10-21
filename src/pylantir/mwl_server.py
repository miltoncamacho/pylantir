#!/usr/bin/env python3

"""
    Author: Milton Camacho
    Date: 2025-01-30
    This script serves as a Modality Worklist (MWL) Service Class Provider (SCP) and a Modality Performed Procedure Step (MPPS) SCP.

    The MWL SCP handles C-FIND requests to query a database for worklist items, returning matching entries.
    The MPPS SCP handles N-CREATE and N-SET requests to manage the status of procedures, updating the database accordingly.

    Key functionalities:
    - MWL C-FIND: Queries the database for worklist items based on the received query dataset and returns matching entries.
    - MPPS N-CREATE: Handles the creation of a new procedure step, ensuring no duplicates and updating the database status to "IN PROGRESS".
    - MPPS N-SET: Handles updates to an existing procedure step, updating the database status to "COMPLETED" or "DISCONTINUED" as appropriate.
"""

import os
import logging
import threading
import time
from pydicom.dataset import Dataset
from pynetdicom import AE, evt
from pynetdicom.sop_class import (
    ModalityWorklistInformationFind,
    ModalityPerformedProcedureStep,
)
from pydicom import dcmread
from pynetdicom import debug_logger
from pynetdicom.dsutils import decode

from pynetdicom.sop_class import Verification
from sqlalchemy import or_

from .db_setup import Session
from .models import WorklistItem

# Allowed Calling AE Titles (Unrestricted for now)
ACCEPTED_CALLING_AETS = []

lgr = logging.getLogger(__name__)

# Track MPPS instances in memory (for reference)
managed_instances = {}
managed_instance_timestamps = {}
managed_instances_lock = threading.Lock()
MPPS_INSTANCE_TTL_SECONDS = int(os.getenv("MPPS_INSTANCE_TTL_SECONDS", "86400"))
MPPS_MAX_MANAGED_INSTANCES = int(os.getenv("MPPS_MAX_MANAGED_INSTANCES", "1000"))


def prune_managed_instances(now=None):
    """Expire abandoned MPPS state and enforce a hard memory bound."""
    current_time = time.monotonic() if now is None else now
    with managed_instances_lock:
        expired = [
            sop_uid
            for sop_uid, created_at in managed_instance_timestamps.items()
            if current_time - created_at >= MPPS_INSTANCE_TTL_SECONDS
        ]
        for sop_uid in expired:
            managed_instances.pop(sop_uid, None)
            managed_instance_timestamps.pop(sop_uid, None)

        overflow = max(0, len(managed_instances) - MPPS_MAX_MANAGED_INSTANCES)
        if overflow:
            oldest = sorted(
                managed_instance_timestamps,
                key=managed_instance_timestamps.get,
            )[:overflow]
            for sop_uid in oldest:
                managed_instances.pop(sop_uid, None)
                managed_instance_timestamps.pop(sop_uid, None)

        remaining = len(managed_instances)

    removed = len(expired) + overflow
    if removed:
        lgr.info(
            "Pruned %s MPPS instance(s); %s remain in memory",
            removed,
            remaining,
        )
    return removed

def row_to_mwl_dataset(row: WorklistItem) -> Dataset:
    """Build MWL item (C-FIND response dataset) from a DB row."""
    ds = Dataset()

    # Standard Patient Attributes
    ds.PatientName = row.patient_name or "UNKNOWN"
    ds.PatientID = row.patient_id or "UNKNOWN"
    # ds.IssuerOfPatientID = row.issuer_of_patient_id
    ds.PatientBirthDate = row.patient_birth_date or ""
    ds.PatientSex = row.patient_sex or ""
    # ds.OtherPatientIDs = row.other_patient_ids or ""
    # ds.PatientAge = row.patient_age or ""
    # ds.PatientSize = row.patient_size or "0"
    ds.PatientWeight = row.patient_weight_lb or "100"
    # ds.MedicalAlerts = row.medical_alerts or ""
    # ds.Allergies = row.allergies or ""
    # ds.AdditionalPatientHistory = row.additional_patient_history or ""
    # ds.PregnancyStatus = row.pregnancy_status or "0"

    # Study-Level Attributes
    ds.StudyInstanceUID = row.study_instance_uid or ""
    # ds.StudyDate = row.study_date or ""
    # ds.StudyTime = row.study_time or ""
    # ds.AccessionNumber = row.accession_number or ""
    ds.ReferringPhysicianName = row.referring_physician_name or ""
    ds.StudyDescription = row.study_description or ""
    # ds.NameOfPhysiciansReadingStudy = row.reading_physicians or ""
    # ds.OperatorsName = row.operators_name or ""

    # Requested Procedure Attributes
    # ds.RequestingPhysician = row.requesting_physician or ""
    # ds.RequestedProcedureDescription = row.requested_procedure_description or "111"
    ds.RequestedProcedureDescription = "111"
    # ds.RequestedProcedureID = row.requested_procedure_id or ""
    ds.RequestedProcedureID = "111"
    # Admission & Patient State
    # ds.AdmissionID = row.admission_id or ""
    # ds.IssuerOfAdmissionID = row.issuer_of_admission_id or ""
    # ds.SpecialNeeds = row.special_needs or ""
    # ds.CurrentPatientLocation = row.current_patient_location or ""
    # ds.PatientState = row.patient_state or ""

    # Scheduled Procedure Step Sequence
    sps = Dataset()
    sps.Modality = row.modality or "MR"
    # sps.ScheduledStationAETitle = row.scheduled_station_aetitle or ""
    sps.ScheduledProcedureStepStartDate = row.scheduled_start_date or ""
    sps.ScheduledProcedureStepStartTime = row.scheduled_start_time or ""
    # sps.ScheduledPerformingPhysicianName = row.performing_physician or ""
    sps.ScheduledProcedureStepDescription = row.protocol_name or "DEFAULT_PROCEDURE"
    sps.ScheduledStationName = row.station_name or ""
    sps.ScheduledProcedureStepStatus = row.performed_procedure_step_status or "SCHEDULED"

    # Protocol Code Sequence
    # you need to map action code (CodeValue) and coding scheme designator (CodingSchemeDesignator) for this to work
    if row.protocol_name:
        protocol_seq = Dataset()
        protocol_seq.CodeValue = row.protocol_name
        # protocol_seq.CodeValue = "CPIP"

        # protocol_seq.ActionCode = "cpipmar03"
        # protocol_seq.CodingSchemeDesignator = "GEHC"
        protocol_seq.CodingSchemeDesignator = row.hisris_coding_designator
        # protocol_seq.CodeMeaning = row.protocol_name
        protocol_seq.CodeMeaning = row.protocol_name
        sps.ScheduledProtocolCodeSequence = [protocol_seq]

    ds.ScheduledProcedureStepSequence = [sps]

    return ds




def handle_mwl_find(event, query_filters=None):
    """Handle MWL C-FIND: query the DB and return matching items."""
    query_ds = event.identifier
    lgr.info(f"Received MWL C-FIND query: {query_ds}")

    session = Session()
    query = session.query(WorklistItem)

    if "PatientName" in query_ds and query_ds.PatientName:
        query = query.filter(WorklistItem.patient_name == str(query_ds.PatientName))
    if "PatientID" in query_ds and query_ds.PatientID:
        query = query.filter(WorklistItem.patient_id == str(query_ds.PatientID))

    # Only return worklist entries that are still scheduled
    query = query.filter(
        or_(
            WorklistItem.performed_procedure_step_status == "SCHEDULED",
            WorklistItem.performed_procedure_step_status == "IN_PROGRESS",
            WorklistItem.performed_procedure_step_status == "DISCONTINUED"
        )
    )

    for query_filter in query_filters or []:
        query = query_filter(query)

    result_count = 0
    try:
        # Avoid retaining every matching ORM row while a modality slowly
        # consumes the response stream.
        for row in query.execution_options(stream_results=True).yield_per(100):
            result_count += 1
            yield (0xFF00, row_to_mwl_dataset(row))

        lgr.info("Found %s matching worklist entries.", result_count)
        yield (0x0000, None)
    finally:
        session.close()


# --------------------------------------------------------------------
# MPPS Handlers (Database Integrated)
# --------------------------------------------------------------------
def handle_mpps_n_create(event):
    """Handles N-CREATE for MPPS (Procedure Start)."""
    req = event.request

    attr_list = event.attribute_list
    ds = Dataset()
    ds.SOPClassUID = ModalityPerformedProcedureStep
    ds.SOPInstanceUID = req.AffectedSOPInstanceUID or "UNKNOWN_UID"
    ds.update(attr_list)

    # Validation logic (log warnings, don't return errors to MRI scanner)
    if not req.AffectedSOPInstanceUID:
        lgr.warning("MPPS N-CREATE: Missing Affected SOP Instance UID")
    prune_managed_instances()
    with managed_instances_lock:
        is_duplicate = ds.SOPInstanceUID in managed_instances
        managed_instances[ds.SOPInstanceUID] = ds
        managed_instance_timestamps[ds.SOPInstanceUID] = time.monotonic()
    if is_duplicate:
        lgr.warning("MPPS N-CREATE: Duplicate SOP Instance UID received")
    prune_managed_instances()

    status = attr_list.get("PerformedProcedureStepStatus", "").upper()
    if not status:
        lgr.warning("MPPS N-CREATE: Missing PerformedProcedureStepStatus")
    elif status != "IN PROGRESS":
        lgr.warning(f"MPPS N-CREATE: Unexpected PerformedProcedureStepStatus = {status}")

    # Update database: Set status to IN_PROGRESS
    patient_id = ds.get("PatientID", None)
    patient_name = ds.get("PatientName", None)
    session = Session()
    try:
        if patient_id:
            if patient_name:
                entry = session.query(WorklistItem).filter_by(
                    patient_id=patient_id,
                    patient_name=str(patient_name),
                ).first()
            else:
                entry = session.query(WorklistItem).filter_by(patient_id=patient_id).first()
            if entry:
                entry.performed_procedure_step_status = "IN_PROGRESS"
                session.commit()
                lgr.info(f"DB updated: PatientID {patient_id} set to IN_PROGRESS")
        else:
            lgr.warning("MPPS N-CREATE: No PatientID found in attributes. DB update skipped.")
    finally:
        session.close()
    lgr.info(f"MPPS N-CREATE processed: {ds.SOPInstanceUID}")

    return 0x0000, ds  # Always return Success

def handle_mpps_n_set(event):
    """Handles N-SET for MPPS (Procedure Completion)."""
    req = event.request
    sop_uid = req.RequestedSOPInstanceUID

    prune_managed_instances()
    with managed_instances_lock:
        ds = managed_instances.get(sop_uid)
    if ds is None:
        lgr.warning(f"MPPS N-SET: Unknown SOP Instance UID {sop_uid}")
        ds = Dataset()
        ds.SOPInstanceUID = sop_uid
        return 0x0000, ds  # Still return success
    mod_list = event.attribute_list
    ds.update(mod_list)

    new_status = ds.get("PerformedProcedureStepStatus", None)
    patient_id = ds.get("PatientID", None)
    patient_name = ds.get("PatientName", None)

    normalized_status = str(new_status).upper() if new_status else ""
    session = Session()
    try:
        if patient_id and new_status:
            if patient_name:
                entry = session.query(WorklistItem).filter_by(
                    patient_id=patient_id,
                    patient_name=str(patient_name),
                ).first()
            else:
                entry = session.query(WorklistItem).filter_by(patient_id=patient_id).first()
            if entry:
                if normalized_status == "COMPLETED":
                    entry.performed_procedure_step_status = "COMPLETED"
                    session.commit()
                    lgr.info(f"DB updated: PatientID: {patient_id} PatientName: {patient_name if patient_name else 'NaN'} set to COMPLETED")
                elif normalized_status == "DISCONTINUED":
                    entry.performed_procedure_step_status = "DISCONTINUED"
                    session.commit()
                    lgr.info(f"DB updated: PatientID: {patient_id} PatientName: {patient_name if patient_name else 'NaN'} set to DISCONTINUED")
                else:
                    lgr.warning(f"MPPS N-SET: Unrecognized status {new_status}")
            else:
                lgr.warning(f"MPPS N-SET: No DB entry found for PatientID: {patient_id} PatientName: {patient_name if patient_name else 'NaN'}")
        else:
            lgr.warning("MPPS N-SET: Missing PatientID or status. No DB update.")
    finally:
        session.close()

    if normalized_status in {"COMPLETED", "DISCONTINUED"}:
        with managed_instances_lock:
            managed_instances.pop(sop_uid, None)
            managed_instance_timestamps.pop(sop_uid, None)
    lgr.info(f"MPPS N-SET processed: {sop_uid} -> {new_status}")

    return 0x0000, ds  # Always return Success



# --------------------------------------------------------------------
# Start MWL + MPPS SCP Server
# --------------------------------------------------------------------
def run_mwl_server(
    host="0.0.0.0",
    port=4242,
    aetitle="MWL_SERVER",
    allowed_aets="",
    query_filters=None,
):
    """Starts an MWL + MPPS SCP."""
    ae = AE(ae_title=aetitle)

    # Add MWL FIND and MPPS support
    ae.add_supported_context(ModalityWorklistInformationFind)
    ae.add_supported_context(ModalityPerformedProcedureStep)
    ae.add_supported_context(Verification)

    # Accept connections only from allowed AE Titles
    ae.require_calling_aet = allowed_aets

    # Register event handlers
    handlers = [
        (evt.EVT_C_FIND, handle_mwl_find, [query_filters]),
        (evt.EVT_N_CREATE, handle_mpps_n_create),
        (evt.EVT_N_SET, handle_mpps_n_set),
    ]

    lgr.info(f"Starting MWL+MPPS SCP on {host}:{port} ...")
    ae.start_server((host, port), block=True, evt_handlers=handlers)


if __name__ == "__main__":
    run_mwl_server()
