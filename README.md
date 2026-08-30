# PMatter

PMatter is a Polyglot v3 (PG3) node server for eISY / IoX that connects to an existing Matter WebSocket server running elsewhere on the network and exposes the discovered devices as ISY nodes.

This project is not a standalone Matter server. It is an integration layer: it expects an upstream implementation such as `python-matter-server` or `matterjs-server` to already be running and reachable over the network.

## What it does

- Connects to a Matter server over WebSocket
- Discovers Matter nodes and endpoints automatically
- Creates an ISY child node for each supported on/off endpoint
- Supports dimmable devices using the Matter LevelControl cluster
- Subscribes to live `attribute_updated` events and pushes updates back to ISY
- Handles standard commands such as ON, OFF, TOGGLE, QUERY, BRIGHTEN, DIM, and FAST ON/OFF
- Reads common power/energy metrics from compatible devices when exposed by the upstream server

## Supported device behavior

The current implementation is geared toward simple Matter devices and dimmers, especially the kinds of devices commonly used in home automation scenarios such as plugs, switches, and bulbs. It has been tested with real-world Tapo devices and is designed to work with the same basic Matter server payloads used by the upstream websocket API.

## Setup

1. Run a Matter server on a machine your eISY can reach over the network.
2. Add your devices to that Matter server and ensure they are online.
3. Install the PMatter PG3 app to your eISY.
4. Open the PG3 configuration for PMatter and set the Matter server `host` and `port`.
5. Save the configuration and restart the node server.
6. PMatter will connect, subscribe to live events, and discover devices automatically.

## Configuration

In the PG3 / Polyglot dashboard, configure:

- `host`: IP address of the machine running the upstream Matter WebSocket server
- `port`: WebSocket port of that server (defaults to `5580` if left blank)

Once configured, the controller node connects, subscribes to live updates, and creates device nodes as endpoints are discovered. You can use the Controller node's `Discover` command to rescan for new devices at any time.

## Project layout

- `pmatter.py` - node server entry point
- `matter_client.py` - background WebSocket client that connects to the upstream Matter server, subscribes to live updates, and sends command payloads
- `nodes/controller.py` - root controller node, config handling, connection setup, and device discovery
- `nodes/matter_device.py` - device and dimmer node logic, command handlers, and live-state updates
- `profile/` - ISY node definitions, editors, and localized strings
- `server.json` - PG3 manifest and configuration metadata
- `support/` - helper scripts and utilities for working with upstream Matter server instances

## Requirements

See `requirements.txt`:

- `udi_interface`
- `websockets`

## Notes

This project focuses on interfacing with an existing Matter server rather than hosting one itself. It is intended to bridge that upstream ecosystem into the ISY / IoX environment while preserving the live status updates and basic automation controls expected by a PG3 node server.
