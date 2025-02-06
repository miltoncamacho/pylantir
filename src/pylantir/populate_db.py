# populate_db.py
from .db_setup import Session
from .models import WorklistItem

def populate_data():
    session = Session()

    # Example 1
    item1 = WorklistItem(
        patient_name="DOE^JOHN",
        patient_id="12345",
        patient_birth_date="19800101",
        patient_sex="M",
        modality="MR",
        scheduled_station_aetitle="MR_STATION",
        scheduled_start_date="20250101",
        scheduled_start_time="083000",
        performing_physician="PERFORMING^PHYSICIAN",
        referring_physician_name="REFERRING^PHYSICIAN",
        procedure_description="MRI BRAIN",
        station_name="MRI_ROOM_1",
        protocol_name="BRAIN_MRI_3T",
        study_instance_uid="1.2.3.4.5.6.7.8.1",
        study_description="MRI BRAIN" # CPIP
    )
    session.add(item1)

    # Example 2
    item2 = WorklistItem(
        patient_name="SMITH^JANE",
        patient_id="67890",
        patient_birth_date="19900202",
        patient_sex="F",
        modality="MR",
        scheduled_station_aetitle="MR_STATION",
        scheduled_start_date="20250102",
        scheduled_start_time="090000",
        performing_physician="DOC^JOHNSON",
        referring_physician_name="REFERRING^PHYSICIAN",
        procedure_description="MRI BRAIN",
        station_name="MRI_ROOM_1",
        protocol_name="BRAIN_MRI_3T",
        study_instance_uid="1.2.3.4.5.6.7.8.2",
        study_description="MRI BRAIN" # CPIP
    )
    session.add(item2)

    # Example 3
    item3 = WorklistItem(
        patient_name="BOND^JAMES",
        patient_id="007",
        patient_birth_date="19251104",
        patient_sex="M",
        modality="MR",
        scheduled_station_aetitle="MR_STATION",
        scheduled_start_date="20250103",
        scheduled_start_time="093000",
        performing_physician="Q^MI6",
        procedure_description="MRI WHOLE BODY",
        station_name="MRI_ROOM_1",
        protocol_name="BRAIN_MRI_3T",
        study_instance_uid="1.2.3.4.5.6.7.8.3",
        study_description="MRI BRAIN" # CPIP
    )
    session.add(item3)

    # Commit
    session.commit()
    session.close()
    print("Populated worklist.db with sample data.")

if __name__ == "__main__":
    populate_data()
