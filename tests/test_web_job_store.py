"""Tests for web_service.job_store — SQLite CRUD and state transitions."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from web_service import job_store as store
from web_service.job_store import (
    STATUS_DONE,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    create_job,
    get_expired_jobs,
    get_job,
    init_db,
    new_job_id,
    purge_job,
    set_done,
    set_expired,
    set_failed,
    set_running,
)


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """Provide a fresh in-memory-style temp DB for each test."""
    db_path = tmp_path / "test_web_service.db"
    init_db(db_path)
    return db_path


@pytest.fixture()
def job_id(db: Path) -> str:
    """Create a queued job and return its ID."""
    jid = new_job_id()
    create_job(jid, "free", "pdf", "epub", "/tmp/job_xyz", db_path=db)
    return jid


class TestInitDb:
    def test_idempotent(self, tmp_path):
        """Running init_db twice must not corrupt the schema."""
        db_path = tmp_path / "idempotent.db"
        init_db(db_path)
        init_db(db_path)  # second call must not raise

        jid = new_job_id()
        create_job(jid, "free", "pdf", "epub", "/tmp/x", db_path=db_path)
        assert get_job(jid, db_path=db_path) is not None


class TestCreateJob:
    def test_creates_queued_job(self, db):
        jid = new_job_id()
        create_job(jid, "free", "pdf", "epub", "/tmp/abc", db_path=db)

        job = get_job(jid, db_path=db)
        assert job is not None
        assert job["status"] == STATUS_QUEUED
        assert job["tier"] == "free"
        assert job["input_fmt"] == "pdf"
        assert job["output_fmt"] == "epub"

    def test_expires_at_uses_ttl(self, db):
        jid = new_job_id()
        before = int(time.time())
        create_job(jid, "free", "pdf", "epub", "/tmp/abc", ttl=3600, db_path=db)
        after = int(time.time())

        job = get_job(jid, db_path=db)
        assert before + 3600 <= job["expires_at"] <= after + 3600


class TestStatusTransitions:
    def test_queued_to_running(self, db, job_id):
        set_running(job_id, db_path=db)
        assert get_job(job_id, db_path=db)["status"] == STATUS_RUNNING

    def test_running_to_done(self, db, job_id):
        set_running(job_id, db_path=db)
        set_done(job_id, "/tmp/output.epub", 512_000, db_path=db)

        job = get_job(job_id, db_path=db)
        assert job["status"] == STATUS_DONE
        assert job["output_path"] == "/tmp/output.epub"
        assert job["output_size"] == 512_000

    def test_running_to_failed(self, db, job_id):
        set_running(job_id, db_path=db)
        set_failed(job_id, "Calibre exited with code 1", db_path=db)

        job = get_job(job_id, db_path=db)
        assert job["status"] == STATUS_FAILED
        assert job["error_msg"] == "Calibre exited with code 1"

    def test_set_expired(self, db, job_id):
        set_expired(job_id, db_path=db)
        assert get_job(job_id, db_path=db)["status"] == STATUS_EXPIRED


class TestGetJob:
    def test_unknown_id_returns_none(self, db):
        assert get_job("00000000-0000-0000-0000-000000000000", db_path=db) is None

    def test_returns_dict(self, db, job_id):
        result = get_job(job_id, db_path=db)
        assert isinstance(result, dict)
        assert "job_id" in result


class TestGetExpiredJobs:
    def test_expired_ttl_returned(self, db):
        jid = new_job_id()
        # ttl=0 → expires_at == created_at → already expired on first check
        create_job(jid, "free", "pdf", "epub", "/tmp/exp", ttl=0, db_path=db)

        expired = get_expired_jobs(db_path=db)
        assert any(j["job_id"] == jid for j in expired)

    def test_active_job_not_returned(self, db, job_id):
        expired = get_expired_jobs(db_path=db)
        assert not any(j["job_id"] == job_id for j in expired)

    def test_already_expired_status_not_returned(self, db):
        jid = new_job_id()
        create_job(jid, "free", "pdf", "epub", "/tmp/exp2", ttl=1, db_path=db)
        time.sleep(1.1)
        set_expired(jid, db_path=db)

        expired = get_expired_jobs(db_path=db)
        assert not any(j["job_id"] == jid for j in expired)


class TestPurgeJob:
    def test_purge_removes_record(self, db, job_id):
        purge_job(job_id, db_path=db)
        assert get_job(job_id, db_path=db) is None
