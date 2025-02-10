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

def row_to_mwl_dataset(row: WorklistItem) -> Dataset:
    """Build MWL item (C-FIND response dataset) from a DB row."""
    ds = Dataset()

    # Standard Patient Attributes
    ds.PatientName = row.patient_name
    ds.PatientID = row.patient_id
    if row.patient_birth_date:
        ds.PatientBirthDate = row.patient_birth_date
    if row.patient_sex:
        ds.PatientSex = row.patient_sex
    if row.study_instance_uid:
        ds.StudyInstanceUID = row.study_instance_uid
    if row.patient_weight_lb:
        ds.PatientWeight = row.patient_weight_lb or "100"
    if row.study_description:
        ds.StudyDescription = row.study_description

    # Protocol-related fields
    if row.protocol_name:
        ds.ProtocolName = row.protocol_name  # (0018,1030)

    # Scheduled Procedure Step Sequence
    sps = Dataset()
    sps.Modality = row.modality or "MR"
    sps.ScheduledStationAETitle = row.scheduled_station_aetitle or ""
    sps.ScheduledProcedureStepStartDate = row.scheduled_start_date or ""
    sps.ScheduledProcedureStepStartTime = row.scheduled_start_time or ""
    sps.ScheduledPerformingPhysicianName = row.performing_physician or ""
    sps.ScheduledProcedureStepDescription = row.procedure_description or "DEFAULT_PROCEDURE"
    sps.ScheduledStationName = row.station_name or ""

    # Adding Local Protocol to Scheduled Protocol Code Sequence. This populates the recomended protocol name in the MWL.
    # TODO: improve the protocol name handling
    if row.protocol_name:
        protocol_seq = Dataset()
        protocol_seq.CodeValue = row.protocol_name[:16]  # Trim long names
        protocol_seq.CodingSchemeDesignator = "LOCAL"
        protocol_seq.CodeMeaning = row.protocol_name
        sps.ScheduledProtocolCodeSequence = [protocol_seq]

    ds.ScheduledProcedureStepSequence = [sps]

    return ds




def handle_mwl_find(event):
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
        or_(WorklistItem.performed_procedure_step_status == "SCHEDULED", WorklistItem.performed_procedure_step_status == "IN_PROGRESS")
    )

    results = query.all()
    session.close()

    lgr.info(f"Found {len(results)} matching worklist entries.")

    for row in results:
        ds = row_to_mwl_dataset(row)
        yield (0xFF00, ds)

    yield (0x0000, None)


# --------------------------------------------------------------------
# MPPS Handlers (Database Integrated)
# --------------------------------------------------------------------
def handle_mpps_n_create(event):
    """Handles N-CREATE for MPPS (Procedure Start)."""
    req = event.request

    if req.AffectedSOPInstanceUID is None:
        lgr.error("MPPS N-CREATE failed: Missing Affected SOP Instance UID")
        return 0x0106, None  # Invalid Attribute Value

    # Prevent duplicate MPPS instances
    if req.AffectedSOPInstanceUID in managed_instances:
        lgr.error("MPPS N-CREATE failed: Duplicate SOP Instance UID")
        return 0x0111, None  # Duplicate SOP Instance

    attr_list = event.attribute_list

    if "PerformedProcedureStepStatus" not in attr_list:
        lgr.error("MPPS N-CREATE failed: Missing PerformedProcedureStepStatus")
        return 0x0120, None  # Missing Attribute
    if attr_list.PerformedProcedureStepStatus.upper() != "IN PROGRESS":
        lgr.error("MPPS N-CREATE failed: Invalid PerformedProcedureStepStatus")
        return 0x0106, None  # Invalid Attribute Value

    ds = Dataset()
    ds.SOPClassUID = ModalityPerformedProcedureStep
    ds.SOPInstanceUID = req.AffectedSOPInstanceUID

    # Copy attributes
    ds.update(attr_list)

    # Store MPPS instance
    managed_instances[ds.SOPInstanceUID] = ds

    # Update database: Set status to IN_PROGRESS
    study_uid = ds.get("StudyInstanceUID", None)
    session = Session()
    if study_uid:
        entry = session.query(WorklistItem).filter_by(study_instance_uid=study_uid).first()
        if entry:
            entry.performed_procedure_step_status = "IN_PROGRESS"
            session.commit()
            lgr.info(f"DB updated: StudyInstanceUID {study_uid} set to IN_PROGRESS")
    session.close()

    lgr.info(f"MPPS N-CREATE success: {ds.SOPInstanceUID} set to IN PROGRESS")

    return 0x0000, ds  # Success


def handle_mpps_n_set(event):
    """Handles N-SET for MPPS (Procedure Completion)."""
    req = event.request
    if req.RequestedSOPInstanceUID not in managed_instances:
        lgr.error("MPPS N-SET failed: SOP Instance not recognized")
        return 0x0112, None  # No Such Object Instance

    ds = managed_instances[req.RequestedSOPInstanceUID]
    mod_list = event.attribute_list

    # Update MPPS instance
    ds.update(mod_list)

    # Log status update
    new_status = ds.get("PerformedProcedureStepStatus", None)
    study_uid = ds.get("StudyInstanceUID", None)

    # Update database
    session = Session()
    if study_uid and new_status:
        entry = session.query(WorklistItem).filter_by(study_instance_uid=study_uid).first()
        if entry:
            if new_status.upper() == "COMPLETED":
                entry.performed_procedure_step_status = "COMPLETED"
                session.commit()
                lgr.info(f"DB updated: StudyInstanceUID {study_uid} set to COMPLETED")
            elif new_status.upper() == "DISCONTINUED":
                entry.performed_procedure_step_status = "DISCONTINUED"
                session.commit()
                lgr.info(f"DB updated: StudyInstanceUID {study_uid} set to DISCONTINUED")
    session.close()

    lgr.info(f"MPPS N-SET success: {req.RequestedSOPInstanceUID} updated to {new_status}")

    return 0x0000, ds  # Success


# --------------------------------------------------------------------
# Start MWL + MPPS SCP Server
# --------------------------------------------------------------------
def run_mwl_server(host="0.0.0.0", port=4242, aetitle="MWL_SERVER", allowed_aets=""):
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
        (evt.EVT_C_FIND, handle_mwl_find),
        (evt.EVT_N_CREATE, handle_mpps_n_create),
        (evt.EVT_N_SET, handle_mpps_n_set),
    ]

    lgr.info(f"Starting MWL+MPPS SCP on {host}:{port} ...")
    ae.start_server((host, port), block=True, evt_handlers=handlers)


if __name__ == "__main__":
    run_mwl_server()
