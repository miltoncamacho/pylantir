from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pylantir.models import Base, WorklistItem
from pylantir.data_sources.redcap_plugin import REDCapPlugin
from pylantir.data_sources.calpendo_plugin import CalendoPlugin


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


def test_redcap_mwl_days_ahead_one_includes_today_and_tomorrow():
    session = make_session()
    session.add_all(
        [
            WorklistItem(patient_id="TODAY", data_source="main_redcap", scheduled_start_date="2026-10-20"),
            WorklistItem(patient_id="TOMORROW", data_source="main_redcap", scheduled_start_date="20261021"),
            WorklistItem(patient_id="LATER", data_source="main_redcap", scheduled_start_date="2026-10-22"),
            WorklistItem(patient_id="OLD", data_source="main_redcap", scheduled_start_date="2026-10-19"),
        ]
    )
    session.commit()

    query_filter = REDCapPlugin().get_mwl_query_filter(
        "main_redcap",
        config={"mwl_days_ahead": 1},
    )
    query = query_filter(session.query(WorklistItem), today=date(2026, 10, 20))

    assert {row.patient_id for row in query.all()} == {"TODAY", "TOMORROW"}


def test_calpendo_today_filter_only_limits_its_own_source():
    session = make_session()
    session.add_all(
        [
            WorklistItem(patient_id="CAL_OLD", data_source="calpendo_main", scheduled_start_date="2026-10-20"),
            WorklistItem(patient_id="CAL_TODAY", data_source="calpendo_main", scheduled_start_date="20261021"),
            WorklistItem(patient_id="CAL_TOMORROW", data_source="calpendo_main", scheduled_start_date="2026-10-22"),
            WorklistItem(patient_id="OTHER_OLD", data_source="main_redcap", scheduled_start_date="2026-10-20"),
        ]
    )
    session.commit()

    query_filter = CalendoPlugin().get_mwl_query_filter(
        "calpendo_main", config={"window_mode": "today"}
    )
    query = query_filter(session.query(WorklistItem), today=date(2026, 10, 21))

    assert {row.patient_id for row in query.all()} == {"CAL_TODAY", "OTHER_OLD"}


def test_calpendo_daily_window_filters_date_and_time():
    session = make_session()
    session.add_all(
        [
            WorklistItem(patient_id="EARLY", data_source="calpendo_main", scheduled_start_date="2026-10-21", scheduled_start_time="08:59"),
            WorklistItem(patient_id="START", data_source="calpendo_main", scheduled_start_date="20261021", scheduled_start_time="0900"),
            WorklistItem(patient_id="INSIDE", data_source="calpendo_main", scheduled_start_date="2026-10-21", scheduled_start_time="16:59"),
            WorklistItem(patient_id="END", data_source="calpendo_main", scheduled_start_date="2026-10-21", scheduled_start_time="17:00"),
        ]
    )
    session.commit()

    query_filter = CalendoPlugin().get_mwl_query_filter(
        "calpendo_main",
        config={"window_mode": "today", "daily_window": {"start_time": [9, 0], "end_time": [17, 0]}},
    )
    query = query_filter(session.query(WorklistItem), today=date(2026, 10, 21))

    assert {row.patient_id for row in query.all()} == {"START", "INSIDE"}
