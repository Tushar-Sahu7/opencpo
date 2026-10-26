"""
OCPP Test base class and TestResult.
"""
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class TestStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class MessageExchange:
    """A single request/response exchange captured during a test."""
    direction: str      # "SENT" or "RECEIVED"
    action: str
    unique_id: str
    payload: Any
    timestamp: str
    raw: str = ""


@dataclass
class TestResult:
    """Result of a single OCPP compliance test."""
    test_name: str
    category: str
    status: TestStatus
    severity: Severity

    # Human-readable outcome
    message: str = ""

    # What the spec says should happen
    expected: str = ""

    # What the charger actually did
    actual: str = ""

    # OCPP spec reference e.g. "OCPP 1.6 §4.1"
    spec_ref: str = ""

    # Raw message exchanges captured during the test
    exchanges: list[MessageExchange] = field(default_factory=list)

    # Fix recommendation for the manufacturer
    fix_recommendation: str = ""

    # Time taken in seconds
    duration_s: float = 0.0

    # Any additional details
    details: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == TestStatus.PASS

    @property
    def failed(self) -> bool:
        return self.status == TestStatus.FAIL

    @property
    def skipped(self) -> bool:
        return self.status == TestStatus.SKIP

    def add_exchange(self, direction: str, action: str, unique_id: str,
                     payload: Any, raw: str = ""):
        import json
        from datetime import datetime, timezone
        self.exchanges.append(MessageExchange(
            direction=direction,
            action=action,
            unique_id=unique_id,
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw=raw,
        ))


class OCPPTest:
    """
    Base class for all OCPP compliance tests.

    Subclasses implement run() and return a TestResult.
    The test has access to the ChargerConnection for sending/receiving messages.
    """
    name: str = "unnamed"
    category: str = "general"
    description: str = ""
    ocpp_spec_ref: str = ""
    severity: Severity = Severity.WARNING
    versions: list[str] = ["1.6", "2.0.1"]

    # Whether this test requires physical interaction
    interactive: bool = False

    # Whether this test should only run if a prior test succeeded
    depends_on: list[str] = []

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._start_time = 0.0

    def skip(self, reason: str = "") -> TestResult:
        return TestResult(
            test_name=self.name,
            category=self.category,
            status=TestStatus.SKIP,
            severity=self.severity,
            message=reason or "Test skipped",
            spec_ref=self.ocpp_spec_ref,
        )

    def result(self, passed: bool, message: str, expected: str = "",
               actual: str = "", fix: str = "",
               exchanges: list = None, details: dict = None) -> TestResult:
        return TestResult(
            test_name=self.name,
            category=self.category,
            status=TestStatus.PASS if passed else TestStatus.FAIL,
            severity=self.severity,
            message=message,
            expected=expected,
            actual=actual,
            spec_ref=self.ocpp_spec_ref,
            exchanges=exchanges or [],
            fix_recommendation=fix,
            duration_s=time.monotonic() - self._start_time,
            details=details or {},
        )

    def error(self, message: str) -> TestResult:
        return TestResult(
            test_name=self.name,
            category=self.category,
            status=TestStatus.ERROR,
            severity=Severity.CRITICAL,
            message=f"Test error: {message}",
            spec_ref=self.ocpp_spec_ref,
            duration_s=time.monotonic() - self._start_time,
        )

    async def run(self, connection) -> TestResult:
        """Override in subclass. Return a TestResult."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement run()")

    async def _run_with_timing(self, connection) -> TestResult:
        """Run the test and record timing."""
        self._start_time = time.monotonic()
        try:
            result = await self.run(connection)
            result.duration_s = time.monotonic() - self._start_time
            return result
        except Exception as e:
            return self.error(str(e))


def make_exchange(direction: str, action: str, uid: str, payload: Any) -> MessageExchange:
    """Convenience function to create a MessageExchange."""
    import json
    from datetime import datetime, timezone
    return MessageExchange(
        direction=direction,
        action=action,
        unique_id=uid,
        payload=payload,
        timestamp=datetime.now(timezone.utc).isoformat(),
        raw=json.dumps([2 if direction == "SENT" else 3, uid, action, payload]),
    )
