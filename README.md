## Matter Node Server (PG3)

A Polyglot v3 node server for the eISY / IoX platform that connects to an
upstream Matter WebSocket server running elsewhere on the network and
exposes the managed Matter devices as ISY nodes.

This project is the PG3 integration layer only: it assumes some Matter
server implementation is already running and reachable, such as
`python-matter-server` or `matterjs-server`. It connects to that server
over its WebSocket API rather than hosting or managing the Matter server
itself. Compatibility depends on the upstream server exposing the same
basic node/event payloads used by this client.

### Files

- `pmatter.py` - node server entry point
- `matter_client.py` - background-thread WebSocket client for the external
  Matter server implementation in use (subscribes to live attribute
  updates, sends commands, handles responses). Logic is based on the
  working `testm.py` prototype.
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

- **host** - IP address of the machine running the upstream Matter
  WebSocket server (e.g. `192.168.2.88`)
- **port** - WebSocket port of the upstream Matter server (default `5580`)

After saving, the node server connects to the already-running upstream
Matter server, subscribes to live events, and runs discovery
automatically, creating one node per Matter on/off endpoint found. Use
the Controller node's **Discover** command to re-scan for new devices at
any time; discovery also runs each long poll.

### Requirements

See `requirements.txt`:

- `udi_interface`
- `websockets`
