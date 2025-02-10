from pylantir.db_setup import Session
from pylantir.models import WorklistItem

def main():
    # Define the target StudyInstanceUID or PatientID
    # target_study_uid = "1.2.3.4.5.6.7.8.3"
    # target_patient_id = "12345"  # Uncomment if you want to filter by patient ID

    # Start a new session
    session = Session()

    # Query the database
    results = session.query(WorklistItem).all()
    # results = session.query(WorklistItem).filter_by(patient_id=target_patient_id).all()  # Filter by patient ID instead

    # Close the session
    session.close()

    # Print results
    if results:
        print(f"Found {len(results)} matching worklist entries:")
        for entry in results:
            print("------------------------------------------------")
            print(f"Patient Name: {entry.patient_name}")
            print(f"Patient ID: {entry.patient_id}")
            print(f"Patient Weight: {entry.patient_weight_lb}")
            print(f"Study Instance UID: {entry.study_instance_uid}")
            print(f"Accession Number: {entry.accession_number}")
            print(f"Modality: {entry.modality}")
            print(f"Study Description: {entry.study_description}")
            print(f"Scheduled AET: {entry.scheduled_station_aetitle}")
            print(f"Scheduled Date: {entry.scheduled_start_date}")
            print(f"Scheduled Time: {entry.scheduled_start_time}")
            print(f"Performing Physician: {entry.performing_physician}")
            print(f"Procedure Description: {entry.procedure_description}")
            print(f"Protocol Name: {entry.protocol_name}")
            print(f"Station Name: {entry.station_name}")
            print(f"Procedure Step Status: {entry.performed_procedure_step_status}")
            print("------------------------------------------------")
    else:
        print("No matching worklist entries found.")

if __name__ == "__main__":
    main()