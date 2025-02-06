# Pylantir

This project's goal is to significantly reduce the number of human-related errors when manualy registering participants for medical imaging procedures.

It effectively provides a python based DICOM Modality Worklist Server (SCP) and Modality Performed Procedure Step (SCP) able to receive requests from medical imaging equipemnt based on DICOM network comunication (e.g., a C-FIND, N-CREATE, N-SET requests).

It will build/update a database based on the information entered in the study-related REDCap database using a REDCap API (You will require to have API access to the study).

## Getting Started

To get started simply install using

```bash
pip install pylantir
```

## Usage

```bash
pylantir start --ip 0.0.0.0 --port 4242 --AE MWL_SERVER
```
