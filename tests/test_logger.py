import json
import logging
import sys

from logger import JsonFormatter, get_logger


def test_json_formatter_standard_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message with %s",
        args=("argument",),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["severity"] == "INFO"
    assert parsed["message"] == "Test message with argument"
    assert parsed["logger"] == "test_logger"
    assert "timestamp" in parsed


def test_json_formatter_extra_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.WARNING,
        pathname="test.py",
        lineno=15,
        msg="Warning occurred",
        args=(),
        exc_info=None,
    )
    record.status_code = 429
    record.category = "rate_limit"
    record.unserializable = object()

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["severity"] == "WARNING"
    assert parsed["status_code"] == 429
    assert parsed["category"] == "rate_limit"
    assert "object at" in parsed["unserializable"]


def test_json_formatter_exception():
    formatter = JsonFormatter()
    exc_info = None
    try:
        raise ValueError("Something broke")
    except ValueError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test_logger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=25,
        msg="Error occurred",
        args=(),
        exc_info=exc_info,
    )
    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["severity"] == "ERROR"
    assert "ValueError: Something broke" in parsed["exception"]

    # Also test record with exc_text pre-set
    record_text = logging.LogRecord(
        name="test_logger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=30,
        msg="Error occurred",
        args=(),
        exc_info=None,
    )
    record_text.exc_text = "Custom traceback string"
    parsed_text = json.loads(formatter.format(record_text))
    assert parsed_text["exception"] == "Custom traceback string"


def test_get_logger_configures_stream_handler(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    unique_name = "test_unique_logger_name_123"

    logger = get_logger(unique_name)
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, JsonFormatter)

    # Calling again does not duplicate handlers
    logger_again = get_logger(unique_name)
    assert len(logger_again.handlers) == 1
