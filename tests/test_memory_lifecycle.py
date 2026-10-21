from pydicom.dataset import Dataset
from types import SimpleNamespace

from pylantir import mwl_server
from pylantir import redcap_to_db


def setup_function():
    with mwl_server.managed_instances_lock:
        mwl_server.managed_instances.clear()
        mwl_server.managed_instance_timestamps.clear()


def teardown_function():
    setup_function()


def test_prune_managed_instances_removes_expired_state(monkeypatch):
    monkeypatch.setattr(mwl_server, "MPPS_INSTANCE_TTL_SECONDS", 60)
    dataset = Dataset()

    with mwl_server.managed_instances_lock:
        mwl_server.managed_instances["expired"] = dataset
        mwl_server.managed_instances["active"] = dataset
        mwl_server.managed_instance_timestamps["expired"] = 100
        mwl_server.managed_instance_timestamps["active"] = 180

    removed = mwl_server.prune_managed_instances(now=200)

    assert removed == 1
    assert set(mwl_server.managed_instances) == {"active"}
    assert set(mwl_server.managed_instance_timestamps) == {"active"}


def test_prune_managed_instances_enforces_hard_cap(monkeypatch):
    monkeypatch.setattr(mwl_server, "MPPS_INSTANCE_TTL_SECONDS", 1000)
    monkeypatch.setattr(mwl_server, "MPPS_MAX_MANAGED_INSTANCES", 2)

    with mwl_server.managed_instances_lock:
        for index in range(3):
            sop_uid = str(index)
            mwl_server.managed_instances[sop_uid] = Dataset()
            mwl_server.managed_instance_timestamps[sop_uid] = index

    removed = mwl_server.prune_managed_instances(now=10)

    assert removed == 1
    assert set(mwl_server.managed_instances) == {"1", "2"}


def test_memory_cleanup_does_not_dispose_shared_pool(monkeypatch):
    monkeypatch.setattr(
        redcap_to_db,
        "get_memory_usage",
        lambda: {"rss_mb": 100.0},
    )
    monkeypatch.setattr(redcap_to_db.gc, "collect", lambda: 0)
    monkeypatch.setattr(
        redcap_to_db.engine.pool,
        "dispose",
        lambda: (_ for _ in ()).throw(AssertionError("pool must remain active")),
    )

    redcap_to_db.cleanup_memory_and_connections()


def test_terminal_n_set_releases_managed_instance(monkeypatch):
    class FakeSession:
        def close(self):
            pass

    dataset = Dataset()
    dataset.SOPInstanceUID = "1.2.3"
    with mwl_server.managed_instances_lock:
        mwl_server.managed_instances["1.2.3"] = dataset
        mwl_server.managed_instance_timestamps["1.2.3"] = mwl_server.time.monotonic()

    attributes = Dataset()
    attributes.PerformedProcedureStepStatus = "COMPLETED"
    event = SimpleNamespace(
        request=SimpleNamespace(RequestedSOPInstanceUID="1.2.3"),
        attribute_list=attributes,
    )
    monkeypatch.setattr(mwl_server, "Session", FakeSession)

    status, _ = mwl_server.handle_mpps_n_set(event)

    assert status == 0x0000
    assert "1.2.3" not in mwl_server.managed_instances
    assert "1.2.3" not in mwl_server.managed_instance_timestamps
