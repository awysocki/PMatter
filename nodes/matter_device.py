"""
ISY node representing a single Matter on/off endpoint (e.g. a smart plug
or switch), driven through the shared MatterClient connection.
"""
import udi_interface

LOGGER = udi_interface.LOGGER


def _command_succeeded(result):
    """
    The python-matter-server 'device_command' response includes an
    'error_code' field. 0 (or absent) means success; any other value
    (e.g. 8 = UNSUPPORTED_ACCESS/failure) means the command was rejected.
    A 'details' string is also populated on validation failures even when
    error_code is 0 (e.g. a missing mandatory field), so treat any
    non-empty details as a failure too.
    """
    if result is None:
        return False
    if "error" in result:
        return False
    error_code = result.get("error_code")
    if error_code not in (None, 0):
        return False
    if result.get("details"):
        return False
    return True


class MatterDevice(udi_interface.Node):
    id = "matterdevice"

    def __init__(self, polyglot, primary, address, name, matter_client,
                 node_id, endpoint_id):
        super(MatterDevice, self).__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.matter = matter_client
        self.node_id = node_id
        self.endpoint_id = endpoint_id

    def start(self):
        self.query()

    def query(self, command=None):
        nodes = self.matter.get_nodes()
        for matter_node in nodes:
            if matter_node.get("node_id") != self.node_id:
                continue
            attributes = matter_node.get("attributes", {}) or {}
            value = attributes.get(f"{self.endpoint_id}/6/0")
            self.setDriver("ST", 1 if value else 0)
            break
        self.reportDrivers()

    def cmd_don(self, command=None):
        result = self.matter.set_onoff(self.node_id, self.endpoint_id, True)
        if not _command_succeeded(result):
            LOGGER.error(
                "DON command failed for node %s endpoint %s: %s",
                self.node_id, self.endpoint_id, result,
            )
            return
        self.setDriver("ST", 1)

    def cmd_dof(self, command=None):
        result = self.matter.set_onoff(self.node_id, self.endpoint_id, False)
        if not _command_succeeded(result):
            LOGGER.error(
                "DOF command failed for node %s endpoint %s: %s",
                self.node_id, self.endpoint_id, result,
            )
            return
        self.setDriver("ST", 0)

    def cmd_toggle(self, command=None):
        self.matter.toggle(self.node_id, self.endpoint_id)

    commands = {
        "DON": cmd_don,
        "DOF": cmd_dof,
        "TOGGLE": cmd_toggle,
        "QUERY": query,
    }

    drivers = [{"driver": "ST", "value": 0, "uom": 2}]


class MatterDimmer(MatterDevice):
    """
    ISY node for a Matter device that supports the LevelControl cluster
    (dimming), e.g. a dimmable light or plug. ST is reported as a
    percentage (UOM 51) instead of the plain boolean on/off (UOM 2)
    used by MatterDevice.
    """

    id = "matterdimmer"

    def __init__(self, *args, **kwargs):
        super(MatterDimmer, self).__init__(*args, **kwargs)
        # Cached last-known on/off + level state, kept in sync from live
        # push events so we never need a blocking network round trip
        # (get_nodes) from the websocket's own background thread - doing
        # so would deadlock that thread until the 10s command timeout.
        self._last_onoff = None
        self._last_level = None

    def query(self, command=None):
        nodes = self.matter.get_nodes()
        for matter_node in nodes:
            if matter_node.get("node_id") != self.node_id:
                continue
            attributes = matter_node.get("attributes", {}) or {}
            is_on = attributes.get(f"{self.endpoint_id}/6/0")
            level = attributes.get(f"{self.endpoint_id}/8/0")
            self._last_onoff = is_on
            self._last_level = level
            self._apply_state()
            break
        self.reportDrivers()

    def on_attribute(self, cluster, attribute, value):
        """
        Update cached on/off + level state directly from a live
        'attribute_updated' push event, and refresh drivers from the
        cache. This is called from the Matter client's own background
        thread, so it must NOT make any blocking send_command/get_nodes
        calls.
        """
        if cluster == "6" and attribute == "0":
            self._last_onoff = value
        elif cluster == "8" and attribute == "0":
            self._last_level = value
        else:
            return
        self._apply_state()
        self.reportDrivers()

    def _apply_state(self):
        """Push the cached on/off + level state to both ST (%) and GV0 (bool)."""
        self.setDriver("ST", self._to_pct(self._last_onoff, self._last_level))
        self.setDriver("GV0", 1 if self._last_onoff else 0)

    @staticmethod
    def _to_pct(is_on, level):
        if not is_on or level is None:
            return 0
        return max(1, round(int(level) * 100 / 254))

    def cmd_don(self, command=None):
        # ISY passes a brightness percentage in command['value'] when the
        # user drags a dimmer slider; a bare "DON" (no value) means 100%.
        query = (command or {}).get("query") or {}
        raw_value = (command or {}).get("value", query.get("value"))
        level_pct = int(raw_value) if raw_value not in (None, "") else 100

        result = self.matter.set_level(self.node_id, self.endpoint_id, level_pct)
        if not _command_succeeded(result):
            LOGGER.error(
                "DON (level %s%%) command failed for node %s endpoint %s: %s",
                level_pct, self.node_id, self.endpoint_id, result,
            )
            return
        self._last_onoff = level_pct > 0
        self._last_level = round(level_pct * 254 / 100)
        self._apply_state()

    def cmd_dof(self, command=None):
        result = self.matter.set_onoff(self.node_id, self.endpoint_id, False)
        if not _command_succeeded(result):
            LOGGER.error(
                "DOF command failed for node %s endpoint %s: %s",
                self.node_id, self.endpoint_id, result,
            )
            return
        self._last_onoff = False
        self._apply_state()

    def cmd_fast_on(self, command=None):
        """ISY 'Fast On' - jump straight to full brightness."""
        result = self.matter.set_level(self.node_id, self.endpoint_id, 100)
        if not _command_succeeded(result):
            LOGGER.error(
                "DFON command failed for node %s endpoint %s: %s",
                self.node_id, self.endpoint_id, result,
            )
            return
        self._last_onoff = True
        self._last_level = 254
        self._apply_state()

    def cmd_fast_off(self, command=None):
        """ISY 'Fast Off' - same as a normal off for a Matter device."""
        self.cmd_dof(command)

    def cmd_brighten(self, command=None):
        result = self.matter.step_level(self.node_id, self.endpoint_id, step_up=True)
        if not _command_succeeded(result):
            LOGGER.error(
                "BRT command failed for node %s endpoint %s: %s",
                self.node_id, self.endpoint_id, result,
            )
            return
        # Don't query() here - it's a blocking get_nodes() round trip that
        # races with (and duplicates) the live attribute_updated push event
        # which already updates ST via on_attribute() moments later.

    def cmd_dim(self, command=None):
        result = self.matter.step_level(self.node_id, self.endpoint_id, step_up=False)
        if not _command_succeeded(result):
            LOGGER.error(
                "DIM command failed for node %s endpoint %s: %s",
                self.node_id, self.endpoint_id, result,
            )
            return
        # See cmd_brighten - rely on the push event instead of querying.

    commands = {
        "DON": cmd_don,
        "DOF": cmd_dof,
        "DFON": cmd_fast_on,
        "DFOF": cmd_fast_off,
        "BRT": cmd_brighten,
        "DIM": cmd_dim,
        "TOGGLE": MatterDevice.cmd_toggle,
        "QUERY": query,
    }

    drivers = [
        {"driver": "ST", "value": 0, "uom": 51},
        {"driver": "GV0", "value": 0, "uom": 25},
    ]
