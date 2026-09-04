# Matter Container & Local Management CLI (`matt`)

A lightweight local management suite and asynchronous Python CLI for controlling Matter devices via a local Matter WebSocket server container running on Linux.

This project is designed to work with Matter server implementations that expose the same client-facing WebSocket API, including `python-matter-server` and `matterjs-server`. The exact backend can vary, but the client expects the same basic node/event data model.

---

## 1. System Overview & Architecture

The Matter WebSocket daemon runs as a stateless, lightweight container inside Podman attached directly to the host network stack (required for IPv6 mDNS device discovery).

* **Host System:** Enterprise Linux / RHEL 9 / Rocky Linux
* **Container Image:** `ghcr.io/matter-js/matterjs-server:latest`
* **Container Name:** `matterjs-server`
* **Persistent Volume:** `matterjs_data`
* **Transport:** Native Host Networking (`--net=host`)
* **WebSocket Endpoint:** `ws://localhost:5580/ws`
* **Clients:** `matt` CLI & custom home automation node servers / bridges

---

## 2. Server Installation & Launch (Podman)

### Prerequisites & Dependencies
* **OS:** Enterprise Linux / RHEL 9 or compatible
* **Container Engine:** Podman
* **Network Requirement:** Active IPv6 interface on the local subnet (required for Matter mDNS discovery)

> **Note:** These steps were tested on Rocky Linux 9. Other RHEL 9 compatible
> distributions (RHEL, AlmaLinux, CentOS Stream, etc.) should work as well,
> but have not been verified directly — use this section as a guide and
> adjust package manager commands as needed for your distribution.

### Initial Setup & Container Deployment

    # 1. Install Podman and enable automatic systemd restarts
    sudo dnf install -y podman
    sudo systemctl enable --now podman-restart

    # 2. Create persistent volume for fabric keys & node state storage
    podman volume create matterjs_data

    # 3. Spin up the MatterJS server container
    podman run -d \
      --name matterjs-server \
      --net=host \
      --restart=always \
      -v matterjs_data:/data \
      ghcr.io/matter-js/matterjs-server:latest

The server listens locally on **`ws://localhost:5580/ws`**.

---

## 3. Network & Firewall Configuration

Matter relies heavily on local IPv6 multicast (mDNS) and UDP transport for device discovery and control.

### Firewall Configuration (`firewalld`)

If `firewalld` is active on your host system, open the Matter WebSocket port (`5580`) and mDNS discovery ports (`5353/udp`):

    # 1. Open local Matter WebSocket server port
    sudo firewall-cmd --permanent --add-port=5580/tcp

    # 2. Open mDNS port for IPv6 device discovery
    sudo firewall-cmd --permanent --add-port=5353/udp

    # 3. Reload firewall rules
    sudo firewall-cmd --reload

### IPv6 Readiness Checklist

Matter **requires** IPv6 enabled on the host network interface:

* **Verify Host IPv6 Address:**
      ip -6 addr show
  *Ensure your primary LAN interface lists a valid Link-Local (`fe80::...`) or Global Unicast IPv6 address.*

* **Check Kernel IPv6 Settings:**
      sysctl net.ipv6.conf.all.disable_ipv6
  *Expected output:* `net.ipv6.conf.all.disable_ipv6 = 0`

* **Verify Container Multicast Routing:**
      podman exec -it matterjs-server ip -6 addr

---

## 4. Repository File Overview

* **`matt`**: Main Bash CLI entry point wrapper.
* **`matter_cli.py`**: Asynchronous Python engine communicating with `matterjs-server` over WebSockets.
* **`raw.py`**: Minimal raw event listener that connects to the MatterJS WebSocket, subscribes to the live event stream, and prints any incoming JSON payloads so you can inspect server behavior and device events in real time.
* **`testm.py`**: Interactive terminal debugging script with live event stream subscription (`attribute_updated` socket pushes).
* **`requirements.txt`**: Python package dependencies for `matter_cli.py`.
* **`install.sh`**: Installs the Python dependencies (via `pip --user`) needed to run the CLI.

### Raw event debugging

Use the `matt` wrapper when you want to inspect every message coming from the Matter server:

  matt monitor
  matt monitor ws://192.168.2.88:5580/ws

It prints one compact line per packet. Button events look like `EVENT node=16 ep=2 cluster=59 event=1 data={'newPosition': 1}`, while large node snapshots are summarized as response counts. You can also run `python3 raw.py [ws://host:5580/ws]` directly.

---

## 5. `matt` CLI Setup & Installation

### Install Python Dependencies

    ./install.sh

This installs the required Python packages (currently just `websockets`)
for the current user via `pip`. Re-run it any time `requirements.txt`
changes.

### Add `matt` to Your PATH

To run `matt` from anywhere in your terminal without typing `python3` or referencing script paths:

    # 1. Make the scripts executable
    chmod +x matt matter_cli.py

    # 2. Copy them to your system path
    sudo cp matt matter_cli.py /usr/local/bin/

---

## 6. `matt` CLI Command Reference

The `matt` CLI provides a small, focused set of shell commands to interact with the local Matter server over WebSockets. Its intent is not to replace a full commissioning or provisioning workflow. In practice, it is used mainly for managing devices that are already defined by their manufacturer programs and are already shared with the fabric. That means adding or removing known shared devices and toggling them once they exist, while full device commissioning belongs above this project’s scope and is handled separately from the helper tooling.

### Device Control
Turn switches ON or OFF directly by Node ID:

    matt on 1       # Turn Node 1 ON
    matt off 1      # Turn Node 1 OFF

### Device Management
Pair, view, or remove Matter devices from the local fabric:

* **List All Devices:**
      matt list
  *Prints all paired Matter nodes, online reachability, serial numbers, and current switch states.*

* **Inspect Device Status:**
      matt status 1
  *Shows detailed hardware metadata, firmware version, vendor name, and power status for Node 1.*

* **Pair / Commission a New Device:**
      matt add 34970112332
      # or using a QR code string:
      matt add MT:Y3.K042C00KA0648A00

* **Remove / Unpair a Device:**
      matt del 1

---

## 7. WebSocket API Payload Reference

All requests send JSON payloads over **`ws://localhost:5580/ws`**.

| Action | Command Payload |
| :--- | :--- |
| **Get Nodes** | `{"message_id": "1", "command": "get_nodes"}` |
| **Start Live Event Subscription** | `{"message_id": "1", "command": "start_listening"}` |
| **Device Control (ON)** | `{"message_id": "1", "command": "device_command", "args": {"node_id": 1, "endpoint_id": 1, "cluster_id": 6, "command_name": "on"}}` |
| **Device Control (OFF)** | `{"message_id": "1", "command": "device_command", "args": {"node_id": 1, "endpoint_id": 1, "cluster_id": 6, "command_name": "off"}}` |
| **Commission Device** | `{"message_id": "1", "command": "commission_with_code", "args": {"code": "34970112332"}}` |
| **Remove Node** | `{"message_id": "1", "command": "remove_node", "args": {"node_id": 1}}` |

### Live Event Push Format
When subscribed via `start_listening`, state changes push in real time:

    {
      "event": "attribute_updated",
      "data": [
        1,       // Node ID
        "1/6/0", // Endpoint 1 / Cluster 6 (On/Off) / Attribute 0 (OnOff)
        true     // New Value (true = ON, false = OFF)
      ]
    }