"""
OCPP Compliance Tester — WebSocket CSMS Server.

Acts as a CSMS (Central System) that chargers connect to.
Accepts connections, negotiates subprotocol, and routes messages
to registered callbacks.

Supports both plain WS and TLS.
"""
import asyncio
import json
import logging
import ssl
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Awaitable

import websockets
from websockets.asyncio.server import ServerConnection

logger = logging.getLogger(__name__)


class MessageLog:
    """Full bidirectional message log with timestamps."""

    def __init__(self):
        self.entries: list[dict] = []

    def log(self, direction: str, raw: str, charger_id: str = ""):
        """Log a raw OCPP message."""
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ts_mono": time.monotonic(),
            "direction": direction,  # "IN" or "OUT"
            "charger_id": charger_id,
            "raw": raw,
            "parsed": parsed,
        }
        self.entries.append(entry)

    def get_action_messages(self, action: str) -> list[dict]:
        """Get all messages with a specific action."""
        result = []
        for e in self.entries:
            if e.get("parsed") and isinstance(e["parsed"], list):
                msg = e["parsed"]
                if len(msg) >= 3 and msg[0] == 2 and msg[2] == action:
                    result.append(e)
                elif len(msg) >= 2:
                    # Check if it's a response to the action
                    pass
        return result

    def get_all(self) -> list[dict]:
        return self.entries.copy()

    def since(self, mono_ts: float) -> list[dict]:
        """Get messages since a monotonic timestamp."""
        return [e for e in self.entries if e["ts_mono"] >= mono_ts]

    def clear(self):
        self.entries.clear()


class ChargerConnection:
    """
    Represents an active charger WebSocket connection.
    Provides send/receive interface for tests.
    """

    def __init__(self, ws, charger_id: str,
                 ocpp_version: str, log: MessageLog):
        self.ws = ws
        self.charger_id = charger_id
        self.ocpp_version = ocpp_version
        self.log = log
        self._pending_results: dict[str, asyncio.Future] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._call_counter = 0
        self._connected = True

        # Charger info populated after BootNotification
        self.vendor: str = ""
        self.model: str = ""
        self.serial: str = ""
        self.firmware: str = ""
        self.boot_payload: dict = {}

        # Active transaction tracking
        self.active_transaction_id: int | None = None
        self.active_connector_id: int | None = None
        self.meter_start: int | None = None

        # Collected status notifications by connector
        self.status_by_connector: dict[int, dict] = {}

        # Config from GetConfiguration
        self.known_config: dict[str, str] = {}

    @property
    def is_connected(self) -> bool:
        return self._connected

    def new_unique_id(self) -> str:
        """Generate a unique message ID."""
        self._call_counter += 1
        return str(uuid.uuid4())[:36]

    async def send_call(self, action: str, payload: dict) -> tuple[str, asyncio.Future]:
        """Send a CALL message, return (unique_id, future for the response)."""
        unique_id = self.new_unique_id()
        msg = json.dumps([2, unique_id, action, payload])
        fut = asyncio.get_event_loop().create_future()
        self._pending_results[unique_id] = fut
        self.log.log("OUT", msg, self.charger_id)
        await self.ws.send(msg)
        return unique_id, fut

    async def send_call_and_wait(self, action: str, payload: dict,
                                  timeout: float = 30.0) -> dict | None:
        """Send a CALL and wait for the CALL_RESULT. Returns payload dict or None on timeout."""
        uid, fut = await self.send_call(action, payload)
        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_results.pop(uid, None)
            return None

    async def send_result(self, unique_id: str, payload: dict):
        """Send a CALL_RESULT."""
        msg = json.dumps([3, unique_id, payload])
        self.log.log("OUT", msg, self.charger_id)
        await self.ws.send(msg)

    async def send_error(self, unique_id: str, error_code: str,
                          description: str = "", details: dict = None):
        """Send a CALL_ERROR."""
        msg = json.dumps([4, unique_id, error_code, description, details or {}])
        self.log.log("OUT", msg, self.charger_id)
        await self.ws.send(msg)

    async def wait_for_action(self, action: str, timeout: float = 30.0) -> dict | None:
        """
        Wait for a CALL with the specified action from the charger.
        Returns the payload dict or None on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                item = await asyncio.wait_for(self._message_queue.get(), timeout=min(remaining, 1.0))
                if item["action"] == action:
                    return item
                else:
                    # Put back items that don't match
                    await self._message_queue.put(item)
                    await asyncio.sleep(0.05)
            except asyncio.TimeoutError:
                pass
        return None

    async def wait_for_any_action(self, actions: list[str], timeout: float = 30.0) -> dict | None:
        """Wait for any of the specified actions."""
        deadline = time.monotonic() + timeout
        collected = []
        try:
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(self._message_queue.get(), timeout=min(remaining, 0.5))
                    if item["action"] in actions:
                        # Put back collected items
                        for c in collected:
                            await self._message_queue.put(c)
                        return item
                    else:
                        collected.append(item)
                except asyncio.TimeoutError:
                    pass
        finally:
            # Restore all non-matching items
            for c in collected:
                await self._message_queue.put(c)
        return None

    def dispatch_incoming(self, msg: list):
        """
        Dispatch an incoming parsed OCPP message.
        Called by the server loop when a message arrives.
        """
        if not isinstance(msg, list) or len(msg) < 2:
            return

        msg_type = msg[0]

        if msg_type == 3:  # CALL_RESULT
            unique_id = msg[1]
            payload = msg[2] if len(msg) > 2 else {}
            fut = self._pending_results.pop(unique_id, None)
            if fut and not fut.done():
                fut.set_result(payload)

        elif msg_type == 4:  # CALL_ERROR
            unique_id = msg[1]
            fut = self._pending_results.pop(unique_id, None)
            if fut and not fut.done():
                error = {
                    "error_code": msg[2] if len(msg) > 2 else "GenericError",
                    "description": msg[3] if len(msg) > 3 else "",
                    "details": msg[4] if len(msg) > 4 else {},
                    "_is_error": True,
                }
                fut.set_result(error)

        elif msg_type == 2:  # CALL from charger
            unique_id = msg[1]
            action = msg[2] if len(msg) > 2 else ""
            payload = msg[3] if len(msg) > 3 else {}
            self._message_queue.put_nowait({
                "unique_id": unique_id,
                "action": action,
                "payload": payload,
                "ts": time.monotonic(),
            })

    def disconnect(self):
        self._connected = False
        # Fail all pending futures
        for fut in self._pending_results.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Charger disconnected"))
        self._pending_results.clear()


class OCPPServer:
    """
    WebSocket server that acts as CSMS for OCPP compliance testing.
    """

    SUPPORTED_SUBPROTOCOLS = ["ocpp1.6", "ocpp2.0.1"]

    def __init__(self, host: str = "0.0.0.0", port: int = 9300,
                 tls_cert: str = None, tls_key: str = None):
        self.host = host
        self.port = port
        self.tls_cert = tls_cert
        self.tls_key = tls_key
        self.log = MessageLog()

        # Active connection (single charger mode)
        self.connection: ChargerConnection | None = None
        self._connect_event = asyncio.Event()

        # Callbacks registered by tests
        self._call_handlers: dict[str, Callable] = {}

        # Default response handlers (send OK to keep charger happy)
        self._default_responses: dict[str, Callable] = {}

        self._server = None

    def register_handler(self, action: str, handler: Callable):
        """Register a handler for a specific OCPP action from charger."""
        self._call_handlers[action] = handler

    def register_default_response(self, action: str, response_fn: Callable):
        """Register a default auto-response for an action (used during passive listening)."""
        self._default_responses[action] = response_fn

    async def wait_for_connection(self, timeout: float = 60.0) -> ChargerConnection | None:
        """Wait for a charger to connect."""
        try:
            await asyncio.wait_for(self._connect_event.wait(), timeout=timeout)
            return self.connection
        except asyncio.TimeoutError:
            return None

    async def _handle_connection(self, ws: ServerConnection):
        """Handle a single charger WebSocket connection."""
        # Extract charger ID from path: /ocpp/{charger_id}
        path = ws.request.path
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "ocpp":
            charger_id = "/".join(parts[1:])
        else:
            charger_id = path.strip("/") or "unknown"

        # Determine OCPP version from negotiated subprotocol
        subprotocol = ws.subprotocol or ""
        if subprotocol == "ocpp1.6":
            ocpp_version = "1.6"
        elif subprotocol == "ocpp2.0.1":
            ocpp_version = "2.0.1"
        else:
            # Accept without subprotocol negotiation (non-compliant but common)
            ocpp_version = "unknown"
            logger.warning(f"[{charger_id}] No subprotocol negotiated — assuming OCPP 1.6")
            ocpp_version = "1.6"

        logger.info(f"Charger connected: {charger_id} (OCPP {ocpp_version}) via {ws.remote_address}")

        conn = ChargerConnection(ws, charger_id, ocpp_version, self.log)
        self.connection = conn
        self._connect_event.set()

        try:
            async for raw_msg in ws:
                self.log.log("IN", raw_msg, charger_id)

                try:
                    msg = json.loads(raw_msg)
                except json.JSONDecodeError as e:
                    logger.warning(f"[{charger_id}] Malformed JSON: {e}")
                    # Don't crash — just log it
                    continue

                # Dispatch to connection
                conn.dispatch_incoming(msg)

                # If it's a CALL, also run any registered handler or default response
                if isinstance(msg, list) and len(msg) >= 3 and msg[0] == 2:
                    unique_id = msg[1]
                    action = msg[2]
                    payload = msg[3] if len(msg) > 3 else {}

                    handler = self._call_handlers.get(action)
                    default = self._default_responses.get(action)

                    if handler:
                        try:
                            response_payload = await handler(conn, unique_id, action, payload)
                            if response_payload is not None:
                                await conn.send_result(unique_id, response_payload)
                        except Exception as e:
                            logger.error(f"[{charger_id}] Handler error for {action}: {e}", exc_info=True)
                            await conn.send_error(unique_id, "InternalError", str(e))
                    elif default:
                        try:
                            response_payload = await default(payload)
                            await conn.send_result(unique_id, response_payload)
                        except Exception as e:
                            logger.error(f"[{charger_id}] Default handler error for {action}: {e}")
                            await conn.send_result(unique_id, {})
                    # If no handler: the test's wait_for_action() will consume it

        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"[{charger_id}] Connection closed: {e}")
        finally:
            conn.disconnect()
            logger.info(f"[{charger_id}] Disconnected")

    async def start(self):
        """Start the WebSocket server."""
        ssl_ctx = None
        if self.tls_cert and self.tls_key:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(self.tls_cert, self.tls_key)
            logger.info(f"TLS enabled with cert: {self.tls_cert}")

        self._server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
            subprotocols=self.SUPPORTED_SUBPROTOCOLS,
            ssl=ssl_ctx,
            ping_interval=None,   # Disabled — some chargers don't respond to WS pings
            ping_timeout=None,
            max_size=65536,
        )

        protocol = "wss" if ssl_ctx else "ws"
        logger.info(f"OCPP server listening on {protocol}://{self.host}:{self.port}/ocpp/{{charger_id}}")

    async def stop(self):
        """Stop the WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("OCPP server stopped")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()
