from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pylantir.models import Base, WorklistItem
from pylantir.data_sources.calpendo_plugin import CalendoPlugin
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
