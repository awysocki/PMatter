"""
ISY node representing a single Matter on/off endpoint (e.g. a smart plug
or switch), driven through the shared MatterClient connection.
"""
import udi_interface

LOGGER = udi_interface.LOGGER


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
        self.matter.set_onoff(self.node_id, self.endpoint_id, True)
        self.setDriver("ST", 1)

    def cmd_dof(self, command=None):
        self.matter.set_onoff(self.node_id, self.endpoint_id, False)
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
