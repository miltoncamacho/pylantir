from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pylantir.models import Base, WorklistItem
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

    upsert_worklist_record(session, original, "calpendo_main")
    session.commit()
    upsert_worklist_record(session, corrected, "calpendo_main")
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

    upsert_worklist_record(session, record, "calpendo_a")
    # Use a distinct patient for the second source so the legacy fallback
    # cannot intentionally claim the first source's row.
    upsert_worklist_record(session, dict(record, patient_id="PATIENT2"), "calpendo_b")
    session.commit()

    assert session.query(WorklistItem).count() == 2


def test_legacy_match_acquires_source_record_id():
    session = make_session()
    session.add(WorklistItem(patient_id="P1", patient_name="^Person"))
    session.commit()

    upsert_worklist_record(
        session,
        {"source_record_id": "55", "patient_id": "P1", "patient_name": "^Person"},
        "calpendo_main",
    )
    session.commit()

    row = session.query(WorklistItem).one()
    assert row.data_source == "calpendo_main"
    assert row.source_record_id == "55"
