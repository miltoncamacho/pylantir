#!/usr/bin/env python3
"""
    Author: Milton Camacho
    Date: 2025-01-30
    This script is designed to test the Modality Performed Procedure Step (MPPS) functionality by simulating a modality device that sends N-CREATE and N-SET requests to a Modality Worklist (MWL) server.

    The script provides two main actions:
    1. N-CREATE: To notify the MWL server that a procedure has started.
    2. N-SET: To update the status of an existing MPPS entry.

    Example usage:

    For N-CREATE:
    python mpps_tester.py create --port 4242 --study_uid 1.2.3.4.5.6.7.8.2

    For N-SET:
    python mpps_tester.py set --port 4242 --study_uid 1.2.3.4.5.6.7.8.2 --status COMPLETED --sop_instance_uid 1.2.840.10008.3.1.2.3.4.92769851149307421510277980557268322762
"""

import logging
import argparse
import uuid
from pydicom.dataset import Dataset
from pynetdicom import AE, debug_logger, evt
from pynetdicom.sop_class import ModalityPerformedProcedureStep

# Enable debug logging
debug_logger()

def generate_sop_instance_uid():
    """Generate a valid Affected SOP Instance UID."""
    return f"1.2.840.10008.3.1.2.3.4.{uuid.uuid4().int}"

def create_mpps(host="localhost", port=11112, calling_aet="TEST_AET", called_aet="MWL_SERVER", study_uid=None):
    """
    Sends an N-CREATE request to notify the MWL server that a procedure has started.
    """
    if study_uid is None:
        print("[ERROR] Missing required parameter: study_uid")
        return None

    ae = AE(ae_title=calling_aet)
    ae.add_requested_context(ModalityPerformedProcedureStep)

    assoc = ae.associate(host, port, ae_title=called_aet)
    if not assoc.is_established:
        print("[ERROR] Association failed!")
        return None

    # Generate a unique Affected SOP Instance UID
    sop_instance_uid = generate_sop_instance_uid()

    # Prepare N-CREATE Dataset
    ds = Dataset()
    ds.SOPInstanceUID = sop_instance_uid  # Required for MPPS
    ds.StudyInstanceUID = study_uid
    ds.PerformedProcedureStepID = "PPS123"
    ds.PerformedStationAETitle = calling_aet
    ds.PerformedProcedureStepStatus = "IN PROGRESS"

    response = assoc.send_n_create(ds, ModalityPerformedProcedureStep, sop_instance_uid)
    status, _ = response

    if status and status.Status == 0x0000:
        print(f"[SUCCESS] MPPS N-CREATE sent for StudyInstanceUID: {study_uid}, SOPInstanceUID: {sop_instance_uid}")
    else:
        print(f"[ERROR] MPPS N-CREATE failed with status: {status}")

    assoc.release()

    return sop_instance_uid  # Return SOPInstanceUID for later use in N-SET

def update_mpps(host="localhost", port=11112, calling_aet="TEST_AET", called_aet="MWL_SERVER",
                study_uid=None, status=None, sop_instance_uid=None):
    """
    Sends an N-SET request to update the status of an existing MPPS entry.
    """
    if study_uid is None:
        print("[ERROR] Missing required parameter: study_uid")
        return
    if status is None:
        print("[ERROR] Missing required parameter: status")
        return
    if sop_instance_uid is None:
        print("[ERROR] Missing required parameter: sop_instance_uid")
        return

    ae = AE(ae_title=calling_aet)
    ae.add_requested_context(ModalityPerformedProcedureStep)

    assoc = ae.associate(host, port, ae_title=called_aet)
    if not assoc.is_established:
        print("[ERROR] Association failed!")
        return

    # Prepare N-SET Dataset
    ds = Dataset()
    ds.StudyInstanceUID = study_uid
    ds.PerformedProcedureStepStatus = status

    response = assoc.send_n_set(ds, ModalityPerformedProcedureStep, sop_instance_uid)
    status, _ = response

    if status and status.Status == 0x0000:
        print(f"[SUCCESS] MPPS N-SET sent for StudyInstanceUID: {study_uid}, SOPInstanceUID: {sop_instance_uid}, Status: {status}")
    else:
        print(f"[ERROR] MPPS N-SET failed with status: {status}")

    assoc.release()

def main(action=None, host="localhost", port=11112, calling_aet="TEST_AET", called_aet="MWL_SERVER",
         study_uid=None, status=None, sop_instance_uid=None):
    """
    Main function to handle MPPS actions.
    """
    if action == "create":
        sop_instance_uid = create_mpps(host, port, calling_aet, called_aet, study_uid)
        if sop_instance_uid:
            print(f"💡 Save this SOPInstanceUID for N-SET: {sop_instance_uid}")

    elif action == "set":
        update_mpps(host, port, calling_aet, called_aet, study_uid, status, sop_instance_uid)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MPPS Tester Script")

    parser.add_argument("action", choices=["create", "set"], help="Choose 'create' to start a procedure, 'set' to update it.")
    parser.add_argument("--host", default="localhost", help="MWL Server IP address (default: localhost)")
    parser.add_argument("--port", type=int, default=11112, help="MWL Server port (default: 11112)")
    parser.add_argument("--calling_aet", default="TEST_AET", help="Your client AE Title (default: TEST_AET)")
    parser.add_argument("--called_aet", default="MWL_SERVER", help="Target server AE Title (default: MWL_SERVER)")
    parser.add_argument("--study_uid", required=True, help="StudyInstanceUID to track.")
    parser.add_argument("--status", choices=["COMPLETED", "DISCONTINUED"], help="Final status for N-SET (Required for 'set' action)")
    parser.add_argument("--sop_instance_uid", help="SOPInstanceUID of the MPPS entry to update (Required for 'set' action)")

    args = parser.parse_args()

    main(
        action=args.action,
        host=args.host,
        port=args.port,
        calling_aet=args.calling_aet,
        called_aet=args.called_aet,
        study_uid=args.study_uid,
        status=args.status,
        sop_instance_uid=args.sop_instance_uid
    )
