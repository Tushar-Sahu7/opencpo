# Writing Tests

Tests are Python classes that inherit from `OCPPTest`. Each test gets a `ChargerConnection` object to send and receive messages.

## Test Class Structure

```python
from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages import v16 as msg16


class MyNewTest(OCPPTest):
    # --- Metadata ---
    name = "my_test_name"            # snake_case, unique within category
    category = "transactions"        # Which category this belongs to
    description = "What this tests"  # Human-readable description
    ocpp_spec_ref = "OCPP 1.6 §4.5" # Spec section reference
    severity = Severity.WARNING       # CRITICAL, WARNING, or INFO
    versions = ["1.6"]               # Which OCPP versions apply

    # Set True if this test needs the user to do something physical
    interactive = False

    async def run(self, connection) -> TestResult:
        # Your test logic here
        ...
```

## Sending Commands

Send a CALL and wait for the CALL_RESULT:

```python
response = await connection.send_call_and_wait(
    action="RemoteStartTransaction",
    payload={
        "connectorId": 1,
        "idTag": self.config.get("rfid", {}).get("valid_tag", "TESTCARD01"),
    },
    timeout=10.0,  # seconds
)
```

If the charger returns a `CALL_ERROR`, the response dict will have `_is_error: True`.

## Returning Results

```python
# Pass
return self.result(
    passed=True,
    message="RemoteStart accepted and session started",
    expected="StartTransaction received within 5s",
    actual=f"Received after {elapsed:.1f}s",
    exchanges=exchanges,  # list of MessageExchange objects
)

# Fail
return self.result(
    passed=False,
    message="No StartTransaction received",
    expected="StartTransaction within 5s of RemoteStart",
    actual="Timeout — no message received",
    fix="Ensure charger starts a transaction when RemoteStart is accepted",
    exchanges=exchanges,
)

# Skip (condition not met — not a failure)
return self.skip("No active transaction — skipping StopTransaction test")
```

## Capturing Message Exchanges

Message exchanges are included in reports to show exactly what was sent and received:

```python
from tests.base import make_exchange

exchanges = []

# Record what you sent
exchanges.append(make_exchange(
    direction="SENT",
    action="RemoteStartTransaction",
    uid=msg_uid,
    payload={"connectorId": 1, "idTag": "TESTCARD01"},
))

# Record what you received
exchanges.append(make_exchange(
    direction="RECEIVED",
    action="StartTransaction",
    uid=rxn_uid,
    payload=start_txn_payload,
))
```

## Waiting for Charger-Initiated Messages

To wait for a message the charger sends spontaneously (not in response to a command):

```python
import asyncio

async def wait_for_start_transaction(connection, timeout=10.0):
    """Wait for the charger to send StartTransaction."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msg = await connection.recv_message(timeout=1.0)
        if msg and msg.get("action") == "StartTransaction":
            return msg
    return None
```

## Full Example Test

```python
import asyncio
from tests.base import OCPPTest, TestResult, Severity, make_exchange
from ocpp_messages import v16 as msg16


class RemoteStartTriggersSession(OCPPTest):
    name = "remote_start_transaction"
    category = "transactions"
    description = "RemoteStartTransaction triggers a StartTransaction from the charger"
    ocpp_spec_ref = "OCPP 1.6 §5.11"
    severity = Severity.CRITICAL
    versions = ["1.6"]

    async def run(self, connection) -> TestResult:
        exchanges = []
        valid_tag = self.config.get("rfid", {}).get("valid_tag", "TESTCARD01")
        max_wait = self.config.get("timing", {}).get("transaction_start_max", 5)

        # Send RemoteStartTransaction
        response = await connection.send_call_and_wait(
            "RemoteStartTransaction",
            {"connectorId": 1, "idTag": valid_tag},
            timeout=10.0,
        )

        if not response:
            return self.result(
                False,
                "No response to RemoteStartTransaction",
                fix="Charger must respond to RemoteStartTransaction",
            )

        exchanges.append(make_exchange(
            "SENT", "RemoteStartTransaction", "rs-1",
            {"connectorId": 1, "idTag": valid_tag}
        ))
        exchanges.append(make_exchange(
            "RECEIVED", "RemoteStartTransaction.conf", "rs-1",
            response
        ))

        if response.get("_is_error") or response.get("status") != "Accepted":
            status = response.get("status", "no status")
            return self.result(
                False,
                f"RemoteStartTransaction returned: {status}",
                expected="status: Accepted",
                actual=f"status: {status}",
                fix="Charger should accept RemoteStartTransaction when connector is Available",
                exchanges=exchanges,
            )

        # Now wait for the charger to send StartTransaction
        start_txn = None
        deadline = asyncio.get_event_loop().time() + max_wait

        while asyncio.get_event_loop().time() < deadline:
            msg = await connection.recv_any(timeout=1.0)
            if msg and msg.get("action") == "StartTransaction":
                start_txn = msg
                break

        if not start_txn:
            return self.result(
                False,
                f"No StartTransaction received within {max_wait}s of RemoteStart",
                expected=f"StartTransaction within {max_wait}s",
                actual="Timeout",
                fix="After accepting RemoteStart, charger must send StartTransaction",
                exchanges=exchanges,
            )

        exchanges.append(make_exchange(
            "RECEIVED", "StartTransaction", start_txn.get("uid", ""),
            start_txn.get("payload", {})
        ))

        # Clean up — stop the transaction
        txn_id = connection.active_transaction_id
        if txn_id:
            await connection.send_call_and_wait(
                "RemoteStopTransaction",
                {"transactionId": txn_id},
                timeout=10.0,
            )

        return self.result(
            True,
            f"StartTransaction received within {max_wait}s",
            exchanges=exchanges,
        )
```

## Registering Your Test

Add your test class to the appropriate category's `ALL_TESTS` list:

```python
# tests/v16/transactions.py

from tests.v16.my_new_test import RemoteStartTriggersSession

ALL_TESTS = [
    # ... existing tests ...
    RemoteStartTriggersSession,
]
```

## Test Configuration Access

Tests receive the full `config.yaml` dict:

```python
# Access timing values
timeout = self.config.get("timing", {}).get("test_timeout", 120)

# Access RFID tags
valid_tag = self.config.get("rfid", {}).get("valid_tag", "TESTCARD01")

# Access charger info
num_connectors = self.config.get("charger", {}).get("num_connectors", 1)
```

## Guidelines

- **One assertion per test** — tests should check one thing clearly
- **Always return a result** — never return `None`, always `self.result()`, `self.skip()`, or `self.error()`
- **Include fix recommendations** — tell the charger manufacturer exactly what to fix
- **Set severity appropriately** — CRITICAL only for things that break basic functionality
- **Use `spec_ref`** — link to the exact OCPP spec section so manufacturers can look it up
- **Handle timeouts gracefully** — use `self.error()` only for unexpected exceptions; use `self.result(False, ...)` for expected-but-wrong outcomes
