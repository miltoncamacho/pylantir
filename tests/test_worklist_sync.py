import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pylantir.models import Base, WorklistItem
from pylantir.data_sources.calpendo_plugin import CalendoPlugin
from pylantir.data_sources.redcap_plugin import REDCapPlugin
from pylantir.data_sources.redcap_concussion_plugin import ConcussionREDCapPlugin
from pylantir.worklist_sync import upsert_worklist_record


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_source_record_id_updates_identifiers_without_duplicate():
    session = make_session()
    original = {
        "source_record_id": "12345",
        "patient_id": "WRONG",
        "patient_name": "^Wrong_Name",
        "scheduled_start_date": "2026-10-15",
        "scheduled_start_time": "09:00",
    }
    corrected = dict(original, patient_id="RIGHT", patient_name="^Right_Name")

    plugin = CalendoPlugin()
    upsert_worklist_record(
        session,
        original,
        "calpendo_main",
        match_candidates=plugin.get_record_match_candidates(original, "calpendo_main"),
    )
    session.commit()
    original_uid = session.query(WorklistItem).one().study_instance_uid
    assert original_uid.startswith("1.2.840.10008.3.1.2.3.4.")
    assert original_uid != original["source_record_id"]
    upsert_worklist_record(
        session,
        corrected,
        "calpendo_main",
        match_candidates=plugin.get_record_match_candidates(corrected, "calpendo_main"),
    )
    session.commit()

    rows = session.query(WorklistItem).all()
    assert len(rows) == 1
    assert rows[0].patient_id == "RIGHT"
    assert rows[0].patient_name == "^Right_Name"
    assert rows[0].source_record_id == "12345"
    assert rows[0].study_instance_uid == original_uid


def test_same_record_id_is_scoped_by_configured_source():
    session = make_session()
    record = {
        "source_record_id": "12345",
        "patient_id": "PATIENT",
        "patient_name": "^Patient",
    }

    plugin = CalendoPlugin()
    upsert_worklist_record(
        session,
        record,
        "calpendo_a",
        match_candidates=plugin.get_record_match_candidates(record, "calpendo_a"),
    )
    # Use a distinct patient for the second source so the legacy fallback
    # cannot intentionally claim the first source's row.
    second = dict(record, patient_id="PATIENT2")
    upsert_worklist_record(
        session,
        second,
        "calpendo_b",
        match_candidates=plugin.get_record_match_candidates(second, "calpendo_b"),
    )
    session.commit()

    assert session.query(WorklistItem).count() == 2


def test_legacy_match_acquires_source_record_id():
    session = make_session()
    session.add(WorklistItem(patient_id="P1", patient_name="^Person"))
    session.commit()

    record = {"source_record_id": "55", "patient_id": "P1", "patient_name": "^Person"}
    plugin = CalendoPlugin()
    upsert_worklist_record(
        session,
        record,
        "calpendo_main",
        match_candidates=plugin.get_record_match_candidates(record, "calpendo_main"),
    )
    session.commit()

    row = session.query(WorklistItem).one()
    assert row.data_source == "calpendo_main"
    assert row.source_record_id == "55"


def test_calpendo_approved_booking_does_not_reset_completed_status():
    session = make_session()
    session.add(
        WorklistItem(
            patient_id="P1",
            patient_name="^Person",
            data_source="calpendo_main",
            source_record_id="55",
            performed_procedure_step_status="COMPLETED",
        )
    )
    session.commit()

    record = {
        "source_record_id": "55",
        "patient_id": "P1",
        "patient_name": "^Person",
        "performed_procedure_step_status": "SCHEDULED",
        "scheduled_start_date": "2026-10-20",
        "scheduled_start_time": "09:00",
    }
    plugin = CalendoPlugin()
    upsert_worklist_record(
        session,
        record,
        "calpendo_main",
        match_candidates=plugin.get_record_match_candidates(record, "calpendo_main"),
        record_preparer=plugin.prepare_record_for_upsert,
    )
    session.commit()

    row = session.query(WorklistItem).one()
    assert row.performed_procedure_step_status == "COMPLETED"
    assert row.scheduled_start_date == "2026-10-20"


def test_calpendo_scheduled_booking_remains_scheduled_when_not_completed():
    plugin = CalendoPlugin()
    record = {"performed_procedure_step_status": "SCHEDULED"}
    existing = WorklistItem(performed_procedure_step_status="IN_PROGRESS")

    prepared = plugin.prepare_record_for_upsert(record, existing)

    assert prepared["performed_procedure_step_status"] == "SCHEDULED"


@pytest.mark.parametrize("plugin_class", [REDCapPlugin, ConcussionREDCapPlugin])
@pytest.mark.parametrize("incoming_status", ["SCHEDULED", "COMPLETED"])
def test_redcap_completed_scan_is_unchanged(plugin_class, incoming_status):
    session = make_session()
    original = WorklistItem(
        patient_id="sub_2368_ses_2a_fam_7324_site_792",
        patient_name="cpip-id-2368^fa-7324",
        study_instance_uid="1.2.3.4.5",
        scheduled_start_date="2026-10-22",
        scheduled_start_time="09:00",
        patient_weight_lb="100",
        protocol_name="CPIP",
        performed_procedure_step_status="COMPLETED",
        data_source="main_redcap",
    )
    session.add(original)
    session.commit()
    before = {column.name: getattr(original, column.name) for column in WorklistItem.__table__.columns}
    record = {
        "patient_id": original.patient_id,
        "patient_name": original.patient_name,
        "study_instance_uid": "1.2.3.4.6",
        "scheduled_start_date": "2026-11-12",
        "scheduled_start_time": "09:30",
        "patient_weight_lb": "47.0",
        "performed_procedure_step_status": incoming_status,
    }
    plugin = plugin_class()
    for _ in range(2):
        upsert_worklist_record(
            session, record, "main_redcap",
            match_candidates=plugin.get_record_match_candidates(record, "main_redcap"),
            record_preparer=plugin.prepare_record_for_upsert,
        )
        session.commit()
        session.expire_all()
        row = session.query(WorklistItem).one()
        assert {column.name: getattr(row, column.name) for column in WorklistItem.__table__.columns} == before
    session.close()


@pytest.mark.parametrize("plugin_class", [REDCapPlugin, ConcussionREDCapPlugin])
def test_redcap_new_and_scheduled_scans_still_sync(plugin_class):
    session = make_session()
    plugin = plugin_class()
    record = {
        "patient_id": "P1", "patient_name": "^Person",
        "scheduled_start_date": "2026-11-12", "scheduled_start_time": "09:00",
        "performed_procedure_step_status": "SCHEDULED",
    }
    for time in ["09:00", "09:30"]:
        record["scheduled_start_time"] = time
        upsert_worklist_record(
            session, record, "main_redcap",
            record_preparer=plugin.prepare_record_for_upsert,
        )
        session.commit()
        row = session.query(WorklistItem).one()
        assert row.scheduled_start_time == time
        assert row.performed_procedure_step_status == "SCHEDULED"
    session.close()
