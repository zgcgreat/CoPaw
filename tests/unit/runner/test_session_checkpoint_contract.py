from swe.app.runner.session_models import (
    SessionCheckpointConflictError,
    SessionCheckpointKey,
    SessionCheckpointRecord,
)


def test_session_checkpoint_conflict_error_keeps_identity_and_versions():
    key = SessionCheckpointKey(
        tenant_id="tenant-a",
        user_id="user-1",
        session_id="console:user-1",
    )

    error = SessionCheckpointConflictError(
        key=key,
        expected_version=2,
        actual_version=3,
    )

    assert error.key == key
    assert error.expected_version == 2
    assert error.actual_version == 3
    assert "tenant-a" in str(error)
    assert "expected=2" in str(error)
    assert "actual=3" in str(error)


def test_session_checkpoint_record_is_immutable():
    record = SessionCheckpointRecord(
        key=SessionCheckpointKey(
            tenant_id="tenant-a",
            user_id="user-1",
            session_id="console:user-1",
        ),
        version=4,
        blob_path="/tmp/checkpoints/user-1_console--user-1.v4.json",
        payload_sha256="a" * 64,
    )

    assert record.version == 4
    assert record.blob_path.endswith(".v4.json")
    assert len(record.payload_sha256) == 64
