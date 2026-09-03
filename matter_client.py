"""
Async client wrapper around the python-matter-server websocket API.

This module is based on the working test script (testm.py) that
validated connectivity, subscriptions, status queries and on/off
commands against a real Tapo S505 Matter device.
"""
import asyncio
import itertools
import json
import threading

import udi_interface
import websockets

LOGGER = udi_interface.LOGGER

# Common Matter cluster/attribute IDs we care about for simple on/off devices
CLUSTER_ONOFF = 6
ATTR_ONOFF = 0
ONOFF_PATH_SUFFIX = "/6/0"

# LevelControl cluster (dimming)
CLUSTER_LEVEL = 8
ATTR_CURRENT_LEVEL = 0
LEVEL_PATH_SUFFIX = "/8/0"
MATTER_LEVEL_MAX = 254  # Matter LevelControl range is 0-254
RECONNECT_DELAY_INITIAL = 2
RECONNECT_DELAY_MAX = 60


class MatterClient:
    """
    Runs its own asyncio event loop in a background thread so it can be
    driven from the synchronous Polyglot node server code, while still
    using an async websocket connection under the hood (same approach
    proven out in testm.py).
    """

    def __init__(self, host, port, on_attribute_update=None, on_event_update=None,
                 on_node_removed=None):
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}/ws"

        self.on_attribute_update = on_attribute_update
        self.on_event_update = on_event_update
        self.on_node_removed = on_node_removed

        self._loop = None
        self._thread = None
        self._ws = None
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._msg_counter = itertools.count(1)
        self._pending = {}
        self._pending_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        """Start the background event loop thread and connect."""
        if self._thread is not None and self._thread.is_alive():
            return self._connected.is_set()
        self._stop.clear()
        self._connected.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        connected = self._connected.wait(timeout=15)
        if not connected:
            LOGGER.error("Timed out connecting to Matter server at %s", self.uri)
        return connected

    def stop(self):
        self._stop.set()
        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._close(), self._loop)
            except RuntimeError:
                pass
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            LOGGER.error("Matter client loop terminated: %s", e)
        finally:
            self._connected.clear()
            self._ws = None
            self._fail_pending()
            self._loop.close()
            self._loop = None

    async def _close(self):
        if self._ws is not None:
            await self._ws.close()

    async def _main(self):
        reconnect_delay = RECONNECT_DELAY_INITIAL
        while not self._stop.is_set():
            try:
                LOGGER.info("Connecting to Matter Server at %s ...", self.uri)
                async with websockets.connect(self.uri, max_size=None) as ws:
                    self._ws = ws
                    # Read initial server handshake payload
                    await ws.recv()

                    # Subscribe to live attribute update events across the fabric
                    await ws.send(
                        json.dumps({"message_id": "sub_1", "command": "start_listening"})
                    )

                    self._connected.set()
                    reconnect_delay = RECONNECT_DELAY_INITIAL
                    LOGGER.info("Connected to Matter server, subscribed to events.")

                    async for message in ws:
                        if self._stop.is_set():
                            break
                        self._handle_message(message)

                if not self._stop.is_set():
                    LOGGER.warning("Matter server websocket closed; reconnecting")
            except Exception as e:
                if not self._stop.is_set():
                    LOGGER.warning("Matter server connection lost: %s", e)
            finally:
                self._connected.clear()
                self._ws = None
                self._fail_pending()

            if not self._stop.is_set():
                LOGGER.info("Retrying Matter server connection in %s seconds", reconnect_delay)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, RECONNECT_DELAY_MAX)

    def _fail_pending(self):
        """Release callers waiting for responses from a disconnected session."""
        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for fut in pending:
            if not fut.done():
                fut.set_result(None)

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------
    def _handle_message(self, message):
        try:
            data = json.loads(message)
        except (ValueError, TypeError):
            LOGGER.warning("Received non-JSON message from Matter server")
            return

        event_type = data.get("event")

        if event_type not in ("attribute_updated", "node_removed"):
            LOGGER.info("Matter server event: %s", data)

        # Live push updates (app / wall button toggles, etc.)
        if event_type == "attribute_updated":
            evt_data = data.get("data", [])
            if len(evt_data) >= 3:
                node_id, attr_path, value = evt_data[0], evt_data[1], evt_data[2]
                if self.on_attribute_update:
                    try:
                        self.on_attribute_update(node_id, attr_path, value)
                    except Exception as e:
                        LOGGER.error("Error in attribute update callback: %s", e)
            return

        if event_type in ("event_updated", "event_occurred", "event_report"):
            evt_data = data.get("data", [])
            if self.on_event_update:
                try:
                    self.on_event_update(evt_data, event_type)
                except Exception as e:
                    LOGGER.error("Error in event update callback: %s", e)
            return

        if event_type == "node_removed":
            node_id = data.get("data")
            if self.on_node_removed and node_id is not None:
                try:
                    self.on_node_removed(node_id)
                except Exception as e:
                    LOGGER.error("Error in node removed callback: %s", e)
            return

        # Direct command / request responses
        message_id = data.get("message_id")
        if message_id is not None:
            with self._pending_lock:
                fut = self._pending.pop(message_id, None)
            if fut is not None and self._loop is not None:
                self._loop.call_soon_threadsafe(fut.set_result, data)

    # ------------------------------------------------------------------
    # Public synchronous API (safe to call from the Polyglot main thread)
    # ------------------------------------------------------------------
    def send_command(self, command, args=None, timeout=10):
        """
        Send a command to the Matter server and block (from the caller's
        thread) until the response arrives or the timeout expires.
        Returns the parsed response dict, or None on failure/timeout.
        """
        if (
            self._loop is None
            or not self._loop.is_running()
            or not self._connected.is_set()
        ):
            LOGGER.error("Matter client is not connected")
            return None

        message_id = f"cmd_{next(self._msg_counter)}"
        payload = {"message_id": message_id, "command": command}
        if args is not None:
            payload["args"] = args

        LOGGER.info("Sending command '%s' args=%s (id=%s)", command, args, message_id)
        future = asyncio.run_coroutine_threadsafe(
            self._send_and_wait(message_id, payload), self._loop
        )
        try:
            result = future.result(timeout=timeout)
            LOGGER.info("Command '%s' (id=%s) response: %s", command, message_id, result)
            return result
        except Exception as e:
            LOGGER.error("Command '%s' (id=%s) failed/timed out: %s", command, message_id, e)
            return None

    async def _send_and_wait(self, message_id, payload):
        if self._ws is None:
            return None
        fut = self._loop.create_future()
        with self._pending_lock:
            self._pending[message_id] = fut
        try:
            await self._ws.send(json.dumps(payload))
        except Exception:
            with self._pending_lock:
                self._pending.pop(message_id, None)
            raise
        return await fut

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------
    def get_nodes(self):
        """Return the list of Matter node dicts known to the server."""
        response = self.send_command("get_nodes")
        if response is None:
            return []
        return response.get("result", []) or []

    def set_onoff(self, node_id, endpoint_id, turn_on):
        return self.send_command(
            "device_command",
            {
                "node_id": node_id,
                "endpoint_id": endpoint_id,
                "cluster_id": CLUSTER_ONOFF,
                "command_name": "On" if turn_on else "Off",
                "payload": {},
            },
        )

    def toggle(self, node_id, endpoint_id):
        return self.send_command(
            "device_command",
            {
                "node_id": node_id,
                "endpoint_id": endpoint_id,
                "cluster_id": CLUSTER_ONOFF,
                "command_name": "Toggle",
                "payload": {},
            },
        )

    def set_level(self, node_id, endpoint_id, level_pct):
        """
        Set brightness via the LevelControl cluster's
        MoveToLevelWithOnOff command (turns the device on/off as needed
        and moves to the target level in one call).

        level_pct: 0-100 (ISY-style percentage). 0 turns the device off.
        """
        level_pct = max(0, min(100, int(level_pct)))
        matter_level = round(level_pct * MATTER_LEVEL_MAX / 100)

        if level_pct <= 0:
            return self.set_onoff(node_id, endpoint_id, False)

        return self.send_command(
            "device_command",
            {
                "node_id": node_id,
                "endpoint_id": endpoint_id,
                "cluster_id": CLUSTER_LEVEL,
                "command_name": "MoveToLevelWithOnOff",
                "payload": {
                    "level": matter_level,
                    "transitionTime": 0,
                    "optionsMask": 0,
                    "optionsOverride": 0,
                },
            },
        )

    def step_level(self, node_id, endpoint_id, step_up, step_size_pct=10):
        """
        Step brightness up/down via the LevelControl cluster's Step
        command (used for ISY Brighten/Dim). step_size_pct is expressed
        as an ISY-style percentage of the 0-254 Matter level range.
        """
        step_size = max(1, round(step_size_pct * MATTER_LEVEL_MAX / 100))
        return self.send_command(
            "device_command",
            {
                "node_id": node_id,
                "endpoint_id": endpoint_id,
                "cluster_id": CLUSTER_LEVEL,
                "command_name": "Step",
                "payload": {
                    "stepMode": 0 if step_up else 1,
                    "stepSize": step_size,
                    "transitionTime": 0,
                    "optionsMask": 0,
                    "optionsOverride": 0,
                },
            },
        )
