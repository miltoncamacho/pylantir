#!/usr/bin/env python3

"""
    Author: Milton Camacho
    Date: 2025-01-30
    This script provides the SQLAlchemy model for the WorklistItem table.
"""
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String
import logging

Base = declarative_base()

lgr = logging.getLogger(__name__)

class WorklistItem(Base):
    __tablename__ = 'worklist_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    study_instance_uid = Column(String(100))
    # Basic patient attributes
    patient_name = Column(String(100))
    patient_id = Column(String(50))
    patient_birth_date = Column(String(8))  # YYYYMMDD
    patient_sex = Column(String(1))         # 'M'/'F' or other
    patient_weight_lb = Column(String(10), default=100)
    accession_number = Column(String(50))

    # Modality worklist attributes
    referring_physician_name = Column(String(100))
    modality = Column(String(10))
    study_description = Column(String(100))
    scheduled_station_aetitle = Column(String(100))
    scheduled_start_date = Column(String(8))  # YYYYMMDD
    scheduled_start_time = Column(String(6))  # HHMMSS
    performing_physician = Column(String(100))
    procedure_description = Column(String(200))
    protocol_name = Column(String(100))
    station_name = Column(String(100))
    try:
        hisris_coding_designator = Column(String(100))
    except:
        lgr.warning("Could not get hisris_coding_designator check models.py ")
    performed_procedure_step_status = Column(String, default="SCHEDULED")


    def __repr__(self):
        return (f"<WorklistItem(id={self.id}, study_instance_uid={self.study_instance_uid}, patient_name={self.patient_name}, "
                f"patient_id={self.patient_id}, modality={self.modality})>")
