import argparse
from pynetdicom import AE
from pynetdicom.sop_class import ModalityWorklistInformationFind
from pydicom.dataset import Dataset

def main(ip="127.0.0.1", port=4242, AEtitle="MWL_SERVER"):
    # Ensure port is an integer
    port = int(port)

    print(f"Running Client Test with IP={ip}, Port={port}, AEtitle={AEtitle}")

    # Create your Application Entity with your desired Calling AE Title
    ae = AE(ae_title=b"AE_TITLE_1")

    # Add MWL FIND context
    ae.add_requested_context(ModalityWorklistInformationFind)

    # Create your C-FIND request dataset
    ds = Dataset()
    ds.PatientName = ""  # Leave empty to match all patients
    ds.Modality = ""     # Leave empty to match all modalities
    ds.ScheduledProcedureStepSequence = [Dataset()]  # Add an empty sequence for broader search

    # Common attributes for matching worklists
    ds.ScheduledProcedureStepSequence[0].ScheduledStationAETitle = ""
    ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate = ""
    ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartTime = ""
    ds.ScheduledProcedureStepSequence[0].Modality = ""
    ds.ScheduledProcedureStepSequence[0].ScheduledPerformingPhysicianName = ""
    ds.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStatus = ""

    # Connect to the MWL server
    assoc = ae.associate(ip, port, ae_title=AEtitle)
    if assoc.is_established:
        print("Association established!")
        # Send the C-FIND request
        responses = assoc.send_c_find(ds, ModalityWorklistInformationFind)
        for status, identifier in responses:
            if status:
                print(f"C-FIND Response Status: 0x{status.Status:04x}")
            if status.Status == 0xFF00:  # Pending response
                print("Matching worklist entry:")
                print(identifier)
            elif status.Status == 0x0000:  # Success
                print("C-FIND query completed successfully.")
            elif status.Status in (0xA700, 0xA900):  # Refused or Error
                print("C-FIND query refused or error.")
            elif status.Status == 0xFE00:  # Cancelled
                print("C-FIND query cancelled.")
        # Release the association
        assoc.release()
        print("Association released.")
    else:
        print("Association failed! Check the IP, port, and AE titles.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DICOM MWL Client Script")
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="IP address of the MWL server")
    parser.add_argument("--port", type=int, default=4242, help="Port of the MWL server")
    parser.add_argument("--AEtitle", type=str, default="MWL_SERVER", help="AE Title of the MWL server")
    args = parser.parse_args()

    main(ip=args.ip, port=args.port, AEtitle=args.AEtitle)
