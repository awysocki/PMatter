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


def parse_energy_attributes(attributes, endpoint_id):
    """
    Extract energy/power metrics (CC, TPW, CV, CA) for a specific endpoint
    from the Matter attributes dictionary.
    Returns a dict like {'CC': 12.5, 'TPW': 1.23, 'CV': 120.1, 'CA': 0.1}
    with any present metrics.
    """
    ep = str(endpoint_id)
    res = {}

    # --- Current Power (CC - Watts) ---
    p_mw = attributes.get(f"{ep}/144/8")
    if p_mw is None:
        p_mw = attributes.get(f"{ep}/144/13")
    if p_mw is not None and isinstance(p_mw, (int, float)):
        res["CC"] = round(p_mw / 1000.0, 2)
    else:
        p_w = attributes.get(f"{ep}/1794/1024")
        if p_w is None:
            p_w = attributes.get(f"{ep}/2820/1291")
        if p_w is None:
            p_w = attributes.get(f"{ep}/2820/0")
        if p_w is not None and isinstance(p_w, (int, float)):
            res["CC"] = round(float(p_w), 2)

    # --- Total Energy (TPW - kWh) ---
    e_raw = attributes.get(f"{ep}/145/0")
    if isinstance(e_raw, dict):
        e_raw = e_raw.get("energy")
    if e_raw is not None and isinstance(e_raw, (int, float)):
        if e_raw > 100000:
            res["TPW"] = round(e_raw / 1000000000.0, 3)
        else:
            res["TPW"] = round(e_raw / 1000.0, 3)
    else:
        e_sm = attributes.get(f"{ep}/1794/0")
        if e_sm is not None and isinstance(e_sm, (int, float)):
            if e_sm > 10000:
                res["TPW"] = round(e_sm / 1000.0, 3)
            else:
                res["TPW"] = round(float(e_sm), 3)

    # --- Voltage (CV - Volts) ---
    v_raw = attributes.get(f"{ep}/144/4")
    if v_raw is None:
        v_raw = attributes.get(f"{ep}/144/11")
    if v_raw is not None and isinstance(v_raw, (int, float)):
        res["CV"] = round(v_raw / 1000.0, 1)
    else:
        v_em = attributes.get(f"{ep}/2820/1285")
        if v_em is not None and isinstance(v_em, (int, float)):
            if v_em > 1000:
                res["CV"] = round(v_em / 1000.0, 1)
            else:
                res["CV"] = round(float(v_em), 1)

    # --- Current (CA - Amps) ---
    i_raw = attributes.get(f"{ep}/144/5")
    if i_raw is None:
        i_raw = attributes.get(f"{ep}/144/12")
    if i_raw is not None and isinstance(i_raw, (int, float)):
        res["CA"] = round(i_raw / 1000.0, 2)
    else:
        i_em = attributes.get(f"{ep}/2820/1288")
        if i_em is not None and isinstance(i_em, (int, float)):
            if i_em > 1000:
                res["CA"] = round(i_em / 1000.0, 2)
            else:
                res["CA"] = round(float(i_em), 2)

    return res


def _parse_energy_event(cluster, attribute, value):
    """
    Parse a single attribute update event for energy/power clusters.
    Returns (driver_id, value) or (None, None).
    """
    if value is None:
        return None, None

    # Cluster 144: Electrical Power Measurement
    if cluster == "144":
        if attribute in ("8", "13") and isinstance(value, (int, float)):
            return "CC", round(value / 1000.0, 2)
        elif attribute in ("4", "11") and isinstance(value, (int, float)):
            return "CV", round(value / 1000.0, 1)
        elif attribute in ("5", "12") and isinstance(value, (int, float)):
            return "CA", round(value / 1000.0, 2)

    # Cluster 145: Electrical Energy Measurement
    elif cluster == "145":
        if attribute == "0":
            val = value.get("energy") if isinstance(value, dict) else value
            if isinstance(val, (int, float)):
                if val > 100000:
                    return "TPW", round(val / 1000000000.0, 3)
                else:
                    return "TPW", round(val / 1000.0, 3)

    # Cluster 1794: Simple Metering
    elif cluster == "1794":
        if attribute == "0" and isinstance(value, (int, float)):
            if value > 10000:
                return "TPW", round(value / 1000.0, 3)
            else:
                return "TPW", round(float(value), 3)
        elif attribute == "1024" and isinstance(value, (int, float)):
            return "CC", round(float(value), 2)

    # Cluster 2820: Electrical Measurement
    elif cluster == "2820":
        if attribute in ("1291", "0") and isinstance(value, (int, float)):
            return "CC", round(float(value), 2)
        elif attribute == "1285" and isinstance(value, (int, float)):
            if value > 1000:
                return "CV", round(value / 1000.0, 1)
            else:
                return "CV", round(float(value), 1)
        elif attribute == "1288" and isinstance(value, (int, float)):
            if value > 1000:
                return "CA", round(value / 1000.0, 2)
            else:
                return "CA", round(float(value), 2)

    return None, None


class MatterDevice(udi_interface.Node):
    id = "matterdevice"

    drivers = [{"driver": "ST", "value": 0, "uom": 2}]

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
            energy_data = parse_energy_attributes(attributes, self.endpoint_id)
            for drv, val in energy_data.items():
                if val is not None:
                    self.setDriver(drv, val)
            break
        self.reportDrivers()

    def on_attribute(self, cluster, attribute, value):
        if cluster == "6" and attribute == "0":
            self.setDriver("ST", 1 if value else 0)
            self.reportDrivers()
        else:
            drv, val = _parse_energy_event(cluster, attribute, value)
            if drv and val is not None:
                self.setDriver(drv, val)
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


class MatterDeviceExt(MatterDevice):
    """Matter on/off device with energy measurement capabilities."""
    id = "matterdevice_ext"

    drivers = [
        {"driver": "ST", "value": 0, "uom": 2},
        {"driver": "CC", "value": 0, "uom": 73},
        {"driver": "TPW", "value": 0, "uom": 33},
        {"driver": "CV", "value": 0, "uom": 72},
        {"driver": "CA", "value": 0, "uom": 1},
    ]


class MatterDimmer(MatterDevice):
    """
    ISY node for a Matter device that supports the LevelControl cluster
    (dimming), e.g. a dimmable light or plug. ST is the plain on/off
    status (UOM 25), matching MatterDevice; GV0 carries the brightness
    percentage (UOM 51).
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
            energy_data = parse_energy_attributes(attributes, self.endpoint_id)
            for drv, val in energy_data.items():
                if val is not None:
                    self.setDriver(drv, val)
            break
        self.reportDrivers()

    def on_attribute(self, cluster, attribute, value):
        """
        Update cached state directly from a live 'attribute_updated' push
        event, and refresh drivers. This is called from the Matter client's
        own background thread, so it must NOT make any blocking send_command
        or get_nodes calls.
        """
        if cluster == "6" and attribute == "0":
            self._last_onoff = value
            self._apply_state()
            self.reportDrivers()
        elif cluster == "8" and attribute == "0":
            self._last_level = value
            self._apply_state()
            self.reportDrivers()
        else:
            drv, val = _parse_energy_event(cluster, attribute, value)
            if drv and val is not None:
                self.setDriver(drv, val)
                self.reportDrivers()

    def _apply_state(self):
        """Push the cached on/off + level state to both ST (on/off) and GV0 (%)."""
        self.setDriver("ST", 1 if self._last_onoff else 0)
        self.setDriver("GV0", self._to_pct(self._last_onoff, self._last_level))

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
        {"driver": "ST", "value": 0, "uom": 2},
        {"driver": "GV0", "value": 0, "uom": 51},
    ]


class MatterDimmerExt(MatterDimmer):
    """Matter dimmer device with energy measurement capabilities."""
    id = "matterdimmer_ext"

    drivers = [
        {"driver": "ST", "value": 0, "uom": 2},
        {"driver": "GV0", "value": 0, "uom": 51},
        {"driver": "CC", "value": 0, "uom": 73},
        {"driver": "TPW", "value": 0, "uom": 33},
        {"driver": "CV", "value": 0, "uom": 72},
        {"driver": "CA", "value": 0, "uom": 1},
    ]


class MatterButton(udi_interface.Node):
    """ISY node for a Matter Switch-cluster button endpoint."""

    id = "matterbutton"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 2},
        {"driver": "GV0", "value": 0, "uom": 25},
    ]

    def __init__(self, polyglot, primary, address, name, matter_client,
                 node_id, endpoint_id):
        super(MatterButton, self).__init__(polyglot, primary, address, name)
        self.matter = matter_client
        self.node_id = node_id
        self.endpoint_id = endpoint_id

    def query(self, command=None):
        self.reportDrivers()

    def on_event(self, cluster, event_id, value=None):
        if cluster != "59":
            return
        try:
            action = int(event_id)
        except (TypeError, ValueError):
            return
        self.setDriver("GV0", action)
        self.setDriver("ST", 1)
        self.reportDrivers()
        self.setDriver("ST", 0)
        self.reportDrivers()

    def on_attribute(self, cluster, attribute, value):
        # Some Matter bridges surface Switch actions as attribute updates.
        if cluster == "59" and attribute in ("0", "1", "2"):
            self.on_event(cluster, attribute, value)

    commands = {"QUERY": query}
