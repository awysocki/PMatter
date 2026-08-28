## Matter Node Server (PG3)

A Polyglot v3 node server for the eISY / IoX platform that connects to a
[python-matter-server](https://github.com/home-assistant-libs/python-matter-server)
instance over its websocket API and exposes discovered Matter devices as
ISY nodes.

### Files

- `pmatter.py` - node server entry point
- `matter_client.py` - background-thread websocket client for the Matter
  server (subscribes to live attribute updates, sends commands, handles
  responses). Logic is based on the working `testm.py` prototype.
- `nodes/controller.py` - root Controller node: reads the `host`/`port`
  custom parameters, connects to the Matter server, discovers nodes and
  creates a child node per on/off endpoint.
- `nodes/matter_device.py` - child node representing one Matter on/off
  endpoint (DON/DOF/TOGGLE/QUERY commands, ST status driver).
- `profile/` - ISY node definitions, editors and NLS strings.
- `server.json` - PG3 manifest, including the `host`/`port` Configuration
  parameters requested from the user in the Polyglot dashboard.

### Configuration

In the Polyglot / PG3 dashboard, open the node server's Configuration tab
and set:

- **host** - IP address of the machine running `python-matter-server`
  (e.g. `192.168.2.88`)
- **port** - websocket port of `python-matter-server` (default `5580`)

After saving, the node server connects, subscribes to live events, and
runs discovery automatically, creating one node per Matter on/off
endpoint found. Use the Controller node's **Discover** command to
re-scan for new devices at any time; discovery also runs each long poll.

### Requirements

See `requirements.txt`:

- `udi_interface`
- `websockets`
