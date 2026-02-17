import logging

from variance import logging_config


def test_session_id_generation():
    session_id = logging_config.generate_session_id()
    assert session_id.startswith("sess_")
    assert len(session_id) > 20


def test_logging_setup_creates_log_file(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(logging_config, "LOG_DIR", log_dir)

    logging_config.setup_logging(console_level="WARNING", file_level="DEBUG")
    logger = logging.getLogger("variance.test")
    logger.info("Test message")

    assert (log_dir / "variance.log").exists()
