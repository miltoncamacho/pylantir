from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pylantir.models import Base, WorklistItem
from pylantir.data_sources.redcap_plugin import REDCapPlugin


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_redcap_results_are_limited_to_current_day_only():
    session = make_session()
    session.add_all(
        [
            WorklistItem(patient_id="TODAY", data_source="main_redcap", scheduled_start_date="2026-10-15"),
            WorklistItem(patient_id="TODAY_DICOM", data_source="main_redcap", scheduled_start_date="20261015"),
            WorklistItem(patient_id="OLD", data_source="main_redcap", scheduled_start_date="2026-10-14"),
            WorklistItem(patient_id="FUTURE", data_source="main_redcap", scheduled_start_date="2026-10-16"),
        ]
    )
    session.commit()

    query_filter = REDCapPlugin().get_mwl_query_filter("main_redcap")
    query = query_filter(session.query(WorklistItem), today=date(2026, 10, 15))

    assert {row.patient_id for row in query.all()} == {"TODAY", "TODAY_DICOM"}


def test_non_redcap_results_are_not_date_limited():
    session = make_session()
    session.add_all(
        [
            WorklistItem(patient_id="REDCAP_OLD", data_source="main_redcap", scheduled_start_date="2026-10-14"),
            WorklistItem(patient_id="CALPENDO_OLD", data_source="calpendo_main", scheduled_start_date="2026-10-14"),
            WorklistItem(patient_id="MANUAL", data_source=None, scheduled_start_date="2026-10-14"),
        ]
    )
    session.commit()

    query_filter = REDCapPlugin().get_mwl_query_filter("main_redcap")
    query = query_filter(session.query(WorklistItem), today=date(2026, 10, 15))

    assert {row.patient_id for row in query.all()} == {"CALPENDO_OLD", "MANUAL"}


def test_legacy_null_source_is_treated_as_redcap():
    session = make_session()
    session.add_all(
        [
            WorklistItem(patient_id="TODAY", data_source=None, scheduled_start_date="2026-10-15"),
            WorklistItem(patient_id="OLD", data_source=None, scheduled_start_date="2026-10-14"),
        ]
    )
    session.commit()

    query_filter = REDCapPlugin().get_mwl_query_filter("REDCap", include_unscoped=True)
    query = query_filter(session.query(WorklistItem), today=date(2026, 10, 15))

    assert [row.patient_id for row in query.all()] == ["TODAY"]
