# Professional Logging Implementation Plan

## Current State Analysis

**Problems:**
- ✅ Basic logging exists (Python `logging` module)
- ❌ No file output - only console/stderr
- ❌ No log rotation - files would grow infinitely
- ❌ No structured logging - hard to parse/query
- ❌ No separation of concerns (app logs vs audit logs vs errors)
- ❌ No contextual enrichment (session IDs, user context, etc.)
- ❌ No log levels per module (everything at same level)
- ❌ No production-ready configuration

**Current Usage:**
```python
# Scattered throughout codebase
logger = logging.getLogger(__name__)
logger.info("Fetching data...")
logger.error(f"Failed: {e}")
```

---

## Professional Logging Architecture

### 1. Log File Structure

```
logs/
├── variance.log                    # Main application log (rotated daily)
├── variance.log.2026-01-01        # Rotated archives
├── variance.log.2025-12-31
├── variance-error.log             # ERROR/CRITICAL only (rotated daily)
├── variance-audit.log             # Audit trail (screening runs, API calls)
├── variance-debug.log             # DEBUG level (when enabled)
└── variance-api.log               # API calls only (for troubleshooting)
```

### 2. Log Levels by Component

| Component | Default Level | Production Level | Notes |
|-----------|---------------|------------------|-------|
| `variance.screening` | INFO | INFO | Screening pipeline steps |
| `variance.market_data` | INFO | WARNING | Market data fetches |
| `variance.tastytrade_client` | INFO | WARNING | API calls |
| `variance.models` | WARNING | WARNING | Model operations |
| `variance.diagnostics` | INFO | INFO | Filter diagnostics |
| `variance.signals` | DEBUG | INFO | Signal generation |
| Root logger | INFO | WARNING | Default for unspecified |

### 3. Log Format

**Standard Format (Human Readable):**
```
2026-01-01 13:45:23.456 | INFO     | variance.screening.pipeline:54 | [session:abc123] Screening started: profile=balanced, symbols=50
2026-01-01 13:45:23.789 | DEBUG    | variance.tastytrade_client:169 | [session:abc123] Fetching metrics for 50 symbols
2026-01-01 13:45:24.123 | WARNING  | variance.market_data.service:89 | [session:abc123] DXLink fallback for /NG: no HV from REST
2026-01-01 13:45:25.456 | ERROR    | variance.screening.filter:234 | [session:abc123] VRP calculation failed for AAPL: division by zero
```

**JSON Format (Machine Parseable - Optional):**
```json
{
  "timestamp": "2026-01-01T13:45:23.456Z",
  "level": "INFO",
  "logger": "variance.screening.pipeline",
  "line": 54,
  "session_id": "abc123",
  "message": "Screening started",
  "context": {
    "profile": "balanced",
    "symbols": 50
  }
}
```

### 4. Contextual Enrichment

**Session ID:**
- Generated per screening run
- Allows correlating all logs for single run
- Format: `sess_20260101_134523_a1b2c3`

**User Context (Future):**
- User ID (if multi-user)
- Account number
- Environment (dev/prod)

**Performance Metrics:**
- Request duration
- API call count
- Cache hit rate

---

## Implementation Details

### Phase 1: Core Logging Infrastructure

#### File 1: `src/variance/logging_config.py`

```python
"""
Professional logging configuration for Variance.

Provides:
- Rotating file handlers
- Multiple log files (app, error, audit, API)
- Structured logging with context
- Per-module log level control
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Log directory
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Session tracking (thread-local storage)
import threading
_session_context = threading.local()


class ContextFilter(logging.Filter):
    """Add session ID and other context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Add session ID if available
        record.session_id = getattr(_session_context, 'session_id', 'N/A')

        # Add performance context if available
        record.duration_ms = getattr(_session_context, 'duration_ms', None)

        return True


class ColoredFormatter(logging.Formatter):
    """Colored console output for development."""

    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'
    }

    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        return super().format(record)


def setup_logging(
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    enable_debug_file: bool = False,
    json_format: bool = False
) -> None:
    """
    Configure application-wide logging.

    Args:
        console_level: Console output level (DEBUG, INFO, WARNING, ERROR)
        file_level: File output level (DEBUG, INFO, WARNING, ERROR)
        enable_debug_file: Whether to create separate debug log file
        json_format: Use JSON format for file logs (for log aggregation tools)

    Example:
        >>> setup_logging(console_level="WARNING", file_level="INFO")
    """

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything, handlers filter

    # Clear existing handlers
    root_logger.handlers.clear()

    # === CONSOLE HANDLER ===
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, console_level.upper()))

    if os.getenv("VARIANCE_NO_COLOR"):
        console_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | [session:%(session_id)s] %(message)s"
        console_formatter = logging.Formatter(console_format, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        console_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | [session:%(session_id)s] %(message)s"
        console_formatter = ColoredFormatter(console_format, datefmt="%Y-%m-%d %H:%M:%S")

    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(ContextFilter())
    root_logger.addHandler(console_handler)

    # === MAIN APP LOG (Rotating Daily) ===
    app_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "variance.log",
        when="midnight",
        interval=1,
        backupCount=30,  # Keep 30 days
        encoding="utf-8"
    )
    app_handler.setLevel(getattr(logging, file_level.upper()))
    app_handler.suffix = "%Y-%m-%d"  # variance.log.2026-01-01

    if json_format:
        # JSON format for machine parsing
        app_handler.setFormatter(JSONFormatter())
    else:
        # Human-readable format
        app_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | [session:%(session_id)s] %(message)s"
        app_handler.setFormatter(logging.Formatter(app_format, datefmt="%Y-%m-%d %H:%M:%S.%f"))

    app_handler.addFilter(ContextFilter())
    root_logger.addHandler(app_handler)

    # === ERROR LOG (Rotating Daily) ===
    error_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "variance-error.log",
        when="midnight",
        interval=1,
        backupCount=90,  # Keep errors for 90 days
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.suffix = "%Y-%m-%d"
    error_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | [session:%(session_id)s] %(message)s\n%(exc_info)s"
    error_handler.setFormatter(logging.Formatter(error_format, datefmt="%Y-%m-%d %H:%M:%S.%f"))
    error_handler.addFilter(ContextFilter())
    root_logger.addHandler(error_handler)

    # === AUDIT LOG (Rotating Daily) ===
    audit_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "variance-audit.log",
        when="midnight",
        interval=1,
        backupCount=365,  # Keep audit trail for 1 year
        encoding="utf-8"
    )
    audit_handler.setLevel(logging.INFO)
    audit_handler.suffix = "%Y-%m-%d"
    audit_format = "%(asctime)s | %(message)s"
    audit_handler.setFormatter(logging.Formatter(audit_format, datefmt="%Y-%m-%d %H:%M:%S"))

    # Audit logger (separate logger)
    audit_logger = logging.getLogger("variance.audit")
    audit_logger.handlers.clear()
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = False  # Don't send to root logger

    # === API LOG (Rotating Daily) ===
    api_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "variance-api.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    api_handler.setLevel(logging.DEBUG)
    api_handler.suffix = "%Y-%m-%d"
    api_format = "%(asctime)s | %(name)s:%(lineno)d | [session:%(session_id)s] %(message)s"
    api_handler.setFormatter(logging.Formatter(api_format, datefmt="%Y-%m-%d %H:%M:%S.%f"))
    api_handler.addFilter(ContextFilter())

    # API logger (captures all API calls)
    api_logger = logging.getLogger("variance.tastytrade_client")
    api_logger.addHandler(api_handler)
    api_logger.setLevel(logging.DEBUG)

    # === DEBUG LOG (Optional, Rotating by Size) ===
    if enable_debug_file:
        debug_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "variance-debug.log",
            maxBytes=50 * 1024 * 1024,  # 50 MB
            backupCount=5,
            encoding="utf-8"
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | [session:%(session_id)s] %(message)s"
        debug_handler.setFormatter(logging.Formatter(debug_format, datefmt="%Y-%m-%d %H:%M:%S.%f"))
        debug_handler.addFilter(ContextFilter())
        root_logger.addHandler(debug_handler)

    # === CONFIGURE MODULE-SPECIFIC LEVELS ===
    logging.getLogger("variance.screening").setLevel(logging.INFO)
    logging.getLogger("variance.market_data").setLevel(logging.INFO)
    logging.getLogger("variance.tastytrade_client").setLevel(logging.INFO)
    logging.getLogger("variance.models").setLevel(logging.WARNING)
    logging.getLogger("variance.signals").setLevel(logging.INFO)

    # Silence noisy third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    root_logger.info("Logging configured", extra={"console_level": console_level, "file_level": file_level})


def set_session_id(session_id: str) -> None:
    """Set session ID for current thread."""
    _session_context.session_id = session_id


def get_session_id() -> Optional[str]:
    """Get session ID for current thread."""
    return getattr(_session_context, 'session_id', None)


def generate_session_id() -> str:
    """Generate unique session ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    import uuid
    short_uuid = str(uuid.uuid4())[:8]
    return f"sess_{timestamp}_{short_uuid}"


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_data = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "line": record.lineno,
            "message": record.getMessage(),
            "session_id": getattr(record, 'session_id', None),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra context if present
        if hasattr(record, 'duration_ms') and record.duration_ms:
            log_data["duration_ms"] = record.duration_ms

        return json.dumps(log_data)


# Convenience function for audit logging
def audit_log(message: str, **context: Any) -> None:
    """
    Write to audit log.

    Example:
        >>> audit_log("Screening completed", profile="balanced", symbols=50, candidates=5)
    """
    logger = logging.getLogger("variance.audit")

    # Format context as key=value pairs
    context_str = " | ".join(f"{k}={v}" for k, v in context.items())
    full_message = f"{message} | {context_str}" if context else message

    logger.info(full_message)
```

---

#### File 2: Update `src/variance/vol_screener.py`

```python
# Add at top of file
from variance.logging_config import setup_logging, set_session_id, generate_session_id, audit_log

def main() -> None:
    # === SETUP LOGGING FIRST ===
    # Check for log level overrides from environment
    console_level = os.getenv("VARIANCE_LOG_LEVEL", "INFO")
    file_level = os.getenv("VARIANCE_FILE_LOG_LEVEL", "DEBUG")
    enable_debug = os.getenv("VARIANCE_DEBUG", "").lower() in ("1", "true", "yes")

    setup_logging(
        console_level=console_level,
        file_level=file_level,
        enable_debug_file=enable_debug
    )

    # Generate session ID
    session_id = generate_session_id()
    set_session_id(session_id)

    logger = logging.getLogger(__name__)
    logger.info(f"Vol Screener started: session_id={session_id}")

    # ... existing argparse code ...

    # === AUDIT LOG: Screening started ===
    audit_log(
        "Screening started",
        session_id=session_id,
        profile=args.profile,
        limit=args.limit,
        show_all=args.show_all,
        debug=args.debug
    )

    try:
        report_data = screen_volatility(config, config_bundle=config_bundle)

        # === AUDIT LOG: Screening completed ===
        if "error" not in report_data:
            audit_log(
                "Screening completed",
                session_id=session_id,
                scanned=report_data['summary']['scanned_symbols_count'],
                candidates=report_data['summary']['candidates_count']
            )
        else:
            audit_log(
                "Screening failed",
                session_id=session_id,
                error=report_data.get('message', 'Unknown error')
            )

        # ... existing output code ...

    except Exception as e:
        logger.exception("Unhandled exception in vol_screener")
        audit_log("Screening crashed", session_id=session_id, error=str(e))
        sys.exit(1)
```

---

#### File 3: Update `src/variance/screening/pipeline.py`

```python
import logging

logger = logging.getLogger(__name__)

class ScreeningPipeline:
    def execute(self) -> dict[str, Any]:
        """Execute screening with detailed logging."""
        import time

        start_time = time.time()
        logger.info("Screening pipeline started")

        try:
            self._load_symbols()
            logger.info(f"Loaded {len(self.ctx.symbols)} symbols from watchlist")

            self._fetch_data()
            logger.info(f"Fetched market data for {len(self.ctx.raw_data)} symbols")

            self._filter_candidates()
            logger.info(
                f"Filtering complete: {len(self.ctx.candidates)} candidates from {len(self.ctx.raw_data)} symbols",
                extra={"pass_rate": f"{len(self.ctx.candidates)/len(self.ctx.raw_data)*100:.1f}%"}
            )

            self._enrich_candidates()
            logger.debug("Enrichment complete")

            self._sort_and_dedupe()
            report = self._build_report()

            elapsed = (time.time() - start_time) * 1000
            logger.info(f"Screening pipeline completed in {elapsed:.0f}ms")

            return report

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Screening pipeline failed after {elapsed:.0f}ms: {e}", exc_info=True)
            raise
```

---

#### File 4: Update `src/variance/tastytrade_client.py`

```python
import logging

logger = logging.getLogger(__name__)

class TastytradeClient:
    def get_market_metrics(self, symbols: list[str]) -> dict[str, TastytradeMetrics]:
        """Fetch with API logging."""
        import time

        start = time.time()
        logger.debug(f"API call: /market-metrics symbols={len(symbols)}")

        try:
            # ... existing code ...

            elapsed_ms = (time.time() - start) * 1000
            logger.info(
                f"API /market-metrics completed: {len(symbols)} symbols in {elapsed_ms:.0f}ms",
                extra={"api_duration_ms": elapsed_ms, "symbols_count": len(symbols)}
            )

            return result

        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            logger.error(
                f"API /market-metrics failed after {elapsed_ms:.0f}ms: {e}",
                exc_info=True,
                extra={"api_duration_ms": elapsed_ms}
            )
            raise
```

---

### Phase 2: Advanced Features

#### 1. Log Analysis Tools

**File:** `scripts/analyze_logs.py`

```python
#!/usr/bin/env python3
"""
Analyze Variance log files.

Usage:
    python scripts/analyze_logs.py --errors           # Show all errors from today
    python scripts/analyze_logs.py --slow-api         # Find slow API calls
    python scripts/analyze_logs.py --session abc123   # Show all logs for session
"""

import argparse
from pathlib import Path
import re
from datetime import datetime, timedelta

def find_errors(log_file: Path, since_hours: int = 24):
    """Extract errors from log file."""
    cutoff = datetime.now() - timedelta(hours=since_hours)

    with open(log_file) as f:
        for line in f:
            # Parse timestamp
            match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if match:
                ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                if ts >= cutoff and "ERROR" in line:
                    print(line.strip())

def find_slow_apis(log_file: Path, threshold_ms: int = 1000):
    """Find API calls slower than threshold."""
    with open(log_file) as f:
        for line in f:
            if "API" in line and "completed" in line:
                # Extract duration
                match = re.search(r"(\d+)ms", line)
                if match and int(match.group(1)) > threshold_ms:
                    print(line.strip())

def filter_by_session(log_file: Path, session_id: str):
    """Show all logs for a specific session."""
    with open(log_file) as f:
        for line in f:
            if f"session:{session_id}" in line:
                print(line.strip())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze Variance logs")
    parser.add_argument("--errors", action="store_true", help="Show recent errors")
    parser.add_argument("--slow-api", action="store_true", help="Find slow API calls")
    parser.add_argument("--session", help="Filter by session ID")
    parser.add_argument("--since-hours", type=int, default=24, help="Look back N hours")

    args = parser.parse_args()

    log_file = Path("logs/variance.log")

    if args.errors:
        find_errors(Path("logs/variance-error.log"), args.since_hours)
    elif args.slow_api:
        find_slow_apis(log_file, threshold_ms=1000)
    elif args.session:
        filter_by_session(log_file, args.session)
    else:
        parser.print_help()
```

#### 2. Log Shipping (Optional)

For centralized log aggregation (Splunk, ELK, Datadog):

```python
# src/variance/logging_config.py

def setup_log_shipping(service_url: str):
    """
    Send logs to external service.

    Example:
        setup_log_shipping("https://logs.example.com/ingest")
    """
    import logging.handlers

    # HTTP handler for log shipping
    http_handler = logging.handlers.HTTPHandler(
        service_url,
        "/",
        method="POST"
    )
    http_handler.setLevel(logging.WARNING)  # Only ship warnings/errors

    root_logger = logging.getLogger()
    root_logger.addHandler(http_handler)
```

---

## Configuration Options

### Environment Variables

```bash
# Log levels
export VARIANCE_LOG_LEVEL=INFO           # Console output level
export VARIANCE_FILE_LOG_LEVEL=DEBUG     # File output level
export VARIANCE_DEBUG=true               # Enable debug log file

# Disable colors (for non-TTY environments)
export VARIANCE_NO_COLOR=1

# JSON logging (for machine parsing)
export VARIANCE_JSON_LOGS=true
```

### Config File (Optional)

**File:** `config/logging_config.yaml`

```yaml
version: 1
disable_existing_loggers: false

formatters:
  standard:
    format: "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | [session:%(session_id)s] %(message)s"
    datefmt: "%Y-%m-%d %H:%M:%S"

  json:
    class: variance.logging_config.JSONFormatter

handlers:
  console:
    class: logging.StreamHandler
    level: INFO
    formatter: standard
    stream: ext://sys.stdout

  app_file:
    class: logging.handlers.TimedRotatingFileHandler
    level: DEBUG
    formatter: standard
    filename: logs/variance.log
    when: midnight
    backupCount: 30

loggers:
  variance.screening:
    level: INFO

  variance.tastytrade_client:
    level: INFO

  variance.models:
    level: WARNING

root:
  level: DEBUG
  handlers: [console, app_file]
```

---

## Testing Plan

### 1. Unit Tests

```python
# tests/test_logging.py

def test_session_id_generation():
    """Test session ID format."""
    from variance.logging_config import generate_session_id

    session_id = generate_session_id()
    assert session_id.startswith("sess_")
    assert len(session_id) > 20

def test_logging_setup():
    """Test logging configuration."""
    from variance.logging_config import setup_logging
    import logging

    setup_logging(console_level="WARNING", file_level="DEBUG")

    logger = logging.getLogger("variance.test")
    logger.info("Test message")

    # Verify log file created
    assert Path("logs/variance.log").exists()
```

### 2. Integration Test

```bash
# Run screener and verify logs created
./screen 10 --debug

# Check log files
ls -lh logs/
# Should show:
# variance.log
# variance-error.log (if errors occurred)
# variance-audit.log
# variance-api.log

# Verify session ID in logs
grep "session:" logs/variance.log | head -5

# Test log rotation (manually)
touch -t 202512310000 logs/variance.log
./screen 10
# Should create variance.log.2025-12-31
```

---

## Rollout Plan

### Phase 1: Core Infrastructure (4 hours)
1. Create `src/variance/logging_config.py` with:
   - File handlers with rotation
   - Context filter for session IDs
   - Module-specific levels
2. Update `vol_screener.py` main():
   - Initialize logging
   - Generate session ID
   - Add audit logging
3. Test basic functionality

### Phase 2: Integration (4 hours)
1. Update all major modules:
   - `screening/pipeline.py`
   - `tastytrade_client.py`
   - `market_data/pure_tastytrade_provider.py`
2. Add performance logging (duration tracking)
3. Add API call logging
4. Test with real screening runs

### Phase 3: Tools & Documentation (2 hours)
1. Create `scripts/analyze_logs.py`
2. Document environment variables
3. Add examples to README
4. Test log analysis tools

### Phase 4: Advanced (Optional, 2 hours)
1. JSON logging support
2. Log shipping setup
3. Metrics extraction

**Total:** 10-12 hours (1.5 days)

---

## Success Criteria

✅ All screening runs write to `logs/variance.log`
✅ Errors automatically captured in `logs/variance-error.log`
✅ Each screening run has unique session ID
✅ Logs rotate daily (don't fill disk)
✅ Old logs auto-deleted after retention period
✅ Can trace full screening run via session ID
✅ API calls logged with duration
✅ Production-ready error handling
✅ Easy to grep/analyze logs for troubleshooting
✅ No performance degradation (<5ms overhead)

---

## Production Considerations

### Disk Space Management

```bash
# Typical disk usage (50 screening runs/day):
# variance.log: ~10 MB/day × 30 days = 300 MB
# variance-error.log: ~1 MB/day × 90 days = 90 MB
# variance-audit.log: ~5 MB/day × 365 days = 1.8 GB
# variance-api.log: ~20 MB/day × 30 days = 600 MB
# Total: ~2.8 GB

# Recommended: Monitor with cron
*/15 * * * * du -sh /path/to/variance/logs/ | mail -s "Log Size" admin@example.com
```

### Log Compression

Add to `logging_config.py`:
```python
# Compress rotated logs
class CompressingTimedRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    def doRollover(self):
        super().doRollover()
        # Compress yesterday's log
        import gzip
        import shutil

        for file in self.baseFilename.parent.glob(f"{self.baseFilename.name}.*"):
            if not file.name.endswith(".gz"):
                with open(file, 'rb') as f_in:
                    with gzip.open(f"{file}.gz", 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                file.unlink()
```

### Security

```python
# Sanitize sensitive data in logs
class SensitiveDataFilter(logging.Filter):
    """Redact API keys, tokens, etc."""

    PATTERNS = [
        (r'token=[\w-]+', 'token=***REDACTED***'),
        (r'api_key=[\w-]+', 'api_key=***REDACTED***'),
        (r'password=[\w-]+', 'password=***REDACTED***'),
    ]

    def filter(self, record):
        import re
        message = record.getMessage()
        for pattern, replacement in self.PATTERNS:
            message = re.sub(pattern, replacement, message)
        record.msg = message
        return True
```
