<div style="text-align: center;">
    <h1>Pylantir</h1>
</div>
<div style="text-align: center;">
    <img src="pylantir.png" alt="Pylantir" width="50%">
</div>

This project's goal is to significantly reduce the number of human-related errors when manualy registering participants for medical imaging procedures.

It effectively provides a python based DICOM Modality Worklist Server (SCP) and Modality Performed Procedure Step (SCP) able to receive requests from medical imaging equipemnt based on DICOM network comunication (e.g., a C-FIND, N-CREATE, N-SET requests).

It will build/update a database based on the information entered in the study-related REDCap database using a REDCap API (You will require to have API access to the study).

## Getting Started

To get started simply install using:

```bash
pip install pylantir
```

You need to provide your REDCap API URL and API token before starting the server.
Set up environmental variables before starting the server:

```bash
export REDCAP_API_URL=<your API url>
export REDCAP_API_TOKEN=<your API token>
```

Start a server called with AEtitle MWL_SERVER.

```bash
pylantir start --ip 127.0.0.1 --port 4242 --AEtitle MWL_SERVER
```

## Tests

Once your modality worklist server is running you can test it running the following:

Query the worklist database to check that you have some entries using:

```bash
pylantir query-db
```

Then, you can get a StudyUID from one of the entries to test the MPPS workflow. For example: 1.2.840.10008.3.1.2.3.4.55635351412689303463019139483773956632

Take this and run a create action to mark the worklist Procedure Step Status as IN_PROGRESS

```bash
pylantir test-mpps --AEtitle MWL_SERVER --mpps_action create --callingAEtitle MWL_TESTER --ip 127.0.0.1 --port 4242 --study_uid 1.2.840.10008.3.1.2.3.4.55635351412689303463019139483773956632
```

You can verify that this in fact modified your database re-running:

```bash
pylantir query-db
```

Finally, you can also simulate the pocedure completion efectively updating the Procedure Step Status to COMPLETED or DISCONTINUED:

```bash
pylantir test-mpps --AEtitle MWL_SERVER --mpps_action set --mpps_status COMPLETED --callingAEtitle MWL_TESTER --ip 127.0.0.1 --port 4242 --study_uid 1.2.840.10008.3.1.2.3.4.55635351412689303463019139483773956632 --sop_uid 1.2.840.10008.3.1.2.3.4.187176383255263644225774937658729238426
```

## Usage

```bash
usage: pylantir [-h] [--AEtitle AETITLE] [--ip IP] [--port PORT] [--pylantir_config PYLANTIR_CONFIG] [--mpps_action {create,set}] [--mpps_status {COMPLETED,DISCONTINUED}] [--callingAEtitle CALLINGAETITLE] [--study_uid STUDY_UID] [--sop_uid SOP_UID] {start,query-db,test-client,test-mpps}
```

**pylantir** - Python DICOM Modality WorkList and Modality Performed Procedure Step compliance

### Positional Arguments:

- **{start,query-db,test-client,test-mpps}**: Command to run:
  - **start**: Start the MWL server
  - **query-db**: Query the MWL database
  - **test-client**: Run tests for MWL
  - **test-mpps**: Run tests for MPPS

### Options:

- **-h, --help**: Show this help message and exit
- **--AEtitle AETITLE**: AE Title for the server
- **--ip IP**: IP/host address for the server
- **--port PORT**: Port for the server
- **--pylantir_config PYLANTIR_CONFIG**: Path to the configuration JSON file containing pylantir configs:
  - **allowed_aet**: List of allowed AE titles e.g. `["MRI_SCANNER", "MRI_SCANNER_2"]`
  - **mri_visit_session_mapping**: Mapping of MRI visit to session e.g., `{"T1": "1", "T2": "2"}`
  - **site**: Site ID:string
  - **protocol**: `{"site": "protocol_name"}`
  - **redcap2wl**: Dictionary of REDCap fields to worklist fields mapping e.g., `{"redcap_field": "worklist_field"}`
- **--mpps_action {create,set}**: Action to perform for MPPS either create or set
- **--mpps_status {COMPLETED,DISCONTINUED}**: Status to set for MPPS either COMPLETED or DISCONTINUED
- **--callingAEtitle CALLINGAETITLE**: Calling AE Title for MPPS, it helps when the MWL is limited to only accept certain AE titles
- **--study_uid STUDY_UID**: StudyInstanceUID to test MPPS
- **--sop_uid SOP_UID**: SOPInstanceUID to test MPPS

## Configuration JSON file

As a default pylantir will try to read a JSON structured file with the following structure:

```json
{
  "db_path": "/path/to/worklist.db",
  "db_echo": "False",
  "db_update_interval": 60,
  "allowed_aet": [],
  "mri_visit_session_mapping": {
    "t1_arm_1": "1",
    "t2_arm_1": "2",
    "t3_arm_1": "3"
  },
  "site": "792",
  "redcap2wl": {
    "study_id": "study_id",
    "family_id": "family_id",
    "youth_dob_y": "youth_dob_y",
    "t1_date": "t1_date",
    "demo_sex": "demo_sex",
    "scheduled_date": "scheduled_start_date",
    "scheduled_time": "scheduled_start_time",
    "mri_wt_lbs": "patient_weight_lb",
    "referring_physician": "referring_physician_name",
    "performing_physician": "performing_physician",
    "station_name": "station_name",
    "status": "performed_procedure_step_status"
  },
  "protocol": {
    "792": "BRAIN_MRI_3T"
  }
}
```

## Clean Stop of the MWL and Database Sync

To cleanly stop the MWL server and ensure the database syncronization properly, press `Ctrl + C` (you might need to press it twice).
