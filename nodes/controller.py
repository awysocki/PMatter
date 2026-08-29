"""
Matter Controller node - the root node for this Polyglot v3 node server.

Handles:
  - Reading user parameters (host/port) via Configuration
  - Connecting to the python-matter-server via MatterClient
  - Discovery: querying nodes and creating a MatterDevice child node
    for each supported Matter device/endpoint
  - Forwarding live attribute-update events to the right child node
"""
import udi_interface

from matter_client import MatterClient
from nodes.matter_device import MatterDevice, MatterDimmer

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom


class Controller(udi_interface.Node):
    id = "controller"

    # Field definitions shown to the user in the "Custom Typed
    # Configuration Parameters" section of the dashboard. These are
    # pushed to Polyglot on start() so the fields exist up front instead
    # of the user having to add them manually.
    TYPED_PARAMS = [
        {
            "name": "host",
            "title": "Matter Server IP Address",
            "isRequired": True,
        },
        {
            "name": "port",
            "title": "Matter Server Port",
            "isRequired": False,
            "defaultValue": "5580",
        },
    ]

    def __init__(self, polyglot, primary, address, name):
        super(Controller, self).__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.host = None
        self.port = None
        self.matter = None
        # node_id (int) -> ISY address (str) map, used to route live events
        self.node_address_map = {}

        self.Notices = Custom(polyglot, "notices")
        self.TypedParameters = Custom(polyglot, "customtypedparams")
        self.TypedData = Custom(polyglot, "customtypeddata")

        self.poly.subscribe(self.poly.START, self.start, address)
        self.poly.subscribe(self.poly.CUSTOMTYPEDPARAMS, self.typedParameterHandler)
        self.poly.subscribe(self.poly.CUSTOMTYPEDDATA, self.typedDataHandler)
        self.poly.subscribe(self.poly.POLL, self.poll)
        self.poly.subscribe(self.poly.STOP, self.stop)

        self.poly.ready()
        self.poly.addNode(self)

    def typedParameterHandler(self, params):
        self.TypedParameters.load(params)

    def typedDataHandler(self, params):
        self.TypedData.load(params)
        self.check_params()

    def check_params(self):
        self.Notices.clear()

        host = (self.TypedData.host or "").strip()
        port = (self.TypedData.port or "").strip()

        if not host:
            self.Notices["host"] = "Please specify the Matter server IP address."
            return
        if not port:
            port = "5580"
        try:
            int(port)
        except ValueError:
            self.Notices["port"] = "Port must be numeric."
            return

        self.host = host
        self.port = port
        LOGGER.info("Configured Matter server at %s:%s", self.host, self.port)

        # (Re)connect now that we have valid parameters
        self.connect_and_discover()

    def start(self):
        LOGGER.info("Started Matter Node Server")
        self.poly.updateProfile()
        self.poly.setCustomParamsDoc()
        # Define the input fields up front so they show up in the
        # dashboard even before the user has entered anything.
        self.TypedParameters.load(self.TYPED_PARAMS, True)
        self.setDriver("ST", 1)
        self.check_params()

    def connect_and_discover(self):
        if self.matter is not None:
            try:
                self.matter.stop()
            except Exception as e:
                LOGGER.warning("Error stopping previous Matter client: %s", e)
            self.matter = None

        self.matter = MatterClient(
            self.host,
            self.port,
            on_attribute_update=self.handle_attribute_update,
            on_node_removed=self.handle_node_removed,
        )

        connected = self.matter.start()
        if not connected:
            self.poly.Notices["conn"] = (
                f"Unable to connect to Matter server at {self.host}:{self.port}"
            )
            self.setDriver("ST", 0)
            return

        self.poly.Notices.clear()
        self.setDriver("ST", 1)
        self.discover()

    def discover(self, *args, **kwargs):
        if self.matter is None:
            LOGGER.warning("Discover called before Matter client is connected")
            return

        nodes = self.matter.get_nodes()
        LOGGER.info("Discovered %d Matter node(s)", len(nodes))

        for matter_node in nodes:
            self.add_device_nodes(matter_node)

    def add_device_nodes(self, matter_node):
        """
        Create a MatterDevice (or MatterDimmer, if the endpoint also
        supports the LevelControl cluster) ISY node for each on/off
        capable endpoint found on a Matter node.
        """
        node_id = matter_node.get("node_id")
        attributes = matter_node.get("attributes", {}) or {}

        if node_id is None:
            return

        # Attribute keys look like "<endpoint>/<cluster>/<attribute>",
        # e.g. "1/6/0" is endpoint 1, OnOff cluster, OnOff attribute.
        # "1/8/0" is endpoint 1, LevelControl cluster, CurrentLevel attribute.
        endpoints_with_onoff = set()
        endpoints_with_level = set()
        for attr_path in attributes.keys():
            parts = attr_path.split("/")
            if len(parts) != 3:
                continue
            try:
                endpoint = int(parts[0])
            except ValueError:
                continue
            if parts[1] == "6":
                endpoints_with_onoff.add(endpoint)
            elif parts[1] == "8":
                endpoints_with_level.add(endpoint)

        if not endpoints_with_onoff:
            LOGGER.debug("Matter node %s has no on/off endpoints, skipping", node_id)
            return

        for endpoint_id in sorted(endpoints_with_onoff):
            address = f"mn{node_id}e{endpoint_id}"
            if address in self.poly.nodes():
                self.node_address_map[node_id] = address
                continue

            name = self._device_name(matter_node, node_id, endpoint_id)
            is_dimmer = endpoint_id in endpoints_with_level
            onoff_path = f"{endpoint_id}/6/0"
            is_on = attributes.get(onoff_path)

            if is_dimmer:
                level = attributes.get(f"{endpoint_id}/8/0")
                initial_state = MatterDimmer._to_pct(is_on, level)
                device = MatterDimmer(
                    self.poly,
                    self.address,
                    address,
                    name,
                    self.matter,
                    node_id,
                    endpoint_id,
                )
                device._last_onoff = is_on
                device._last_level = level
            else:
                initial_state = 1 if is_on else 0
                device = MatterDevice(
                    self.poly,
                    self.address,
                    address,
                    name,
                    self.matter,
                    node_id,
                    endpoint_id,
                )

            self.poly.addNode(device)
            device.setDriver("ST", initial_state)
            if is_dimmer:
                device.setDriver("GV0", 1 if is_on else 0)
            self.node_address_map[node_id] = address
            LOGGER.info(
                "Added Matter %s node '%s' (node %s endpoint %s)",
                "dimmer" if is_dimmer else "device",
                name,
                node_id,
                endpoint_id,
            )

    @staticmethod
    def _device_name(matter_node, node_id, endpoint_id):
        for key in ("name", "device_name", "product_name"):
            value = matter_node.get(key)
            if value:
                return f"{value} {endpoint_id}" if endpoint_id != 1 else value
        return f"MNode {node_id}-{endpoint_id}"

    def handle_attribute_update(self, node_id, attr_path, value):
        """Called from the MatterClient background thread."""
        address = self.node_address_map.get(node_id)
        if address is None:
            return

        node = self.poly.getNode(address)
        if node is None:
            return

        parts = attr_path.split("/")
        if len(parts) != 3:
            return
        cluster, attribute = parts[1], parts[2]

        if isinstance(node, MatterDimmer):
            # OnOff and CurrentLevel arrive as separate events. Update the
            # node's cached state directly from the event data - do NOT
            # call node.query()/get_nodes() here, since this callback runs
            # on the Matter client's own background thread and a blocking
            # send_command from that thread would deadlock until timeout.
            node.on_attribute(cluster, attribute, value)
        elif cluster == "6" and attribute == "0":
            node.setDriver("ST", 1 if value else 0)

    def handle_node_removed(self, node_id):
        address = self.node_address_map.pop(node_id, None)
        if address is not None:
            LOGGER.info("Matter node %s was removed", node_id)

    def poll(self, poll_type):
        if poll_type == "longPoll" and self.matter is not None:
            self.discover()

    def stop(self):
        if self.matter is not None:
            self.matter.stop()
        LOGGER.info("Matter Node Server stopped")

    def query(self, command=None):
        self.reportDrivers()

    commands = {"DISCOVER": discover, "QUERY": query}

    drivers = [{"driver": "ST", "value": 1, "uom": 2}]
