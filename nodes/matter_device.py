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
    """
    if result is None:
        return False
    if "error" in result:
        return False
    error_code = result.get("error_code")
    if error_code not in (None, 0):
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

    def query(self, command=None):
        nodes = self.matter.get_nodes()
        for matter_node in nodes:
            if matter_node.get("node_id") != self.node_id:
                continue
            attributes = matter_node.get("attributes", {}) or {}
            is_on = attributes.get(f"{self.endpoint_id}/6/0")
            level = attributes.get(f"{self.endpoint_id}/8/0")
            self.setDriver("ST", self._to_pct(is_on, level))
            break
        self.reportDrivers()

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
        self.setDriver("ST", level_pct)

    def cmd_dof(self, command=None):
        result = self.matter.set_onoff(self.node_id, self.endpoint_id, False)
        if not _command_succeeded(result):
            LOGGER.error(
                "DOF command failed for node %s endpoint %s: %s",
                self.node_id, self.endpoint_id, result,
            )
            return
        self.setDriver("ST", 0)

    commands = {
        "DON": cmd_don,
        "DOF": cmd_dof,
        "TOGGLE": MatterDevice.cmd_toggle,
        "QUERY": query,
    }

    drivers = [{"driver": "ST", "value": 0, "uom": 51}]
