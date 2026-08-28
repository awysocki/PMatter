#!/usr/bin/env python3
"""Matter CLI Backend Engine.

Handles WebSocket IPC commands to python-matter-server.
"""

import asyncio
import json
import sys
import websockets

SERVER_URI = "ws://localhost:5580/ws"


async def send_command(payload):
  try:
    async with websockets.connect(SERVER_URI) as ws:
      await ws.recv()  # Consume handshake
      await ws.send(json.dumps(payload))
      res = await ws.recv()
      return json.loads(res)
  except Exception as e:
    print(f"Error connecting to Matter server: {e}")
    sys.exit(1)


async def cmd_add(code):
  print(f"Initiating commissioning for code: {code}...")
  payload = {
      "message_id": "req_add",
      "command": "commission_with_code",
      "args": {"code": code},
  }
  res = await send_command(payload)

  if "error" in res:
    print(f"❌ Failed: {res['error']}")
  else:
    node_id = res.get("result", {}).get("node_id", "Unknown")
    print(f"✅ Device paired successfully! Assigned Node ID: {node_id}")


async def cmd_del(node_id):
  try:
    node_num = int(node_id)
  except ValueError:
    print("❌ Error: Node ID must be a number.")
    return

  print(f"Removing Node {node_num} from Matter fabric...")
  payload = {
      "message_id": "req_del",
      "command": "remove_node",
      "args": {"node_id": node_num},
  }
  res = await send_command(payload)

  if "error" in res:
    print(f"❌ Removal Failed: {res['error']}")
  else:
    print(f"✅ Node {node_num} successfully removed.")


async def cmd_list():
  payload = {"message_id": "req_list", "command": "get_nodes"}
  res = await send_command(payload)

  nodes = res.get("result", [])
  if not nodes:
    print("No paired devices found.")
    return

  print("\n================ PAIRED MATTER DEVICES ================")
  for n in nodes:
    nid = n.get("node_id")
    avail = "ONLINE 🟢" if n.get("available") else "OFFLINE 🔴"
    attrs = n.get("attributes", {})

    vendor = attrs.get("0/40/1", "Unknown Vendor")
    product = attrs.get("0/40/3", "Unknown Product")
    serial = attrs.get("0/40/15", "N/A")
    is_on = attrs.get("1/6/0")
    state_str = (
        "ON 💡" if is_on is True else "OFF 🔌" if is_on is False else "N/A"
    )

    print(f" Node ID {nid}: {vendor} {product} [{avail}]")
    print(f"   Serial: {serial} | State: {state_str}")
    print("-" * 55)


async def cmd_status(node_id):
  try:
    node_num = int(node_id)
  except ValueError:
    print("❌ Error: Node ID must be a number.")
    return

  payload = {"message_id": "req_status", "command": "get_nodes"}
  res = await send_command(payload)

  nodes = res.get("result", [])
  target = next((n for n in nodes if n.get("node_id") == node_num), None)

  if not target:
    print(f"❌ Node ID {node_num} not found on server.")
    return

  attrs = target.get("attributes", {})
  vendor = attrs.get("0/40/1", "Unknown")
  product = attrs.get("0/40/3", "Unknown")
  serial = attrs.get("0/40/15", "Unknown")
  fw = attrs.get("0/40/10", "Unknown")
  is_on = attrs.get("1/6/0")
  state_str = "ON 💡" if is_on is True else "OFF 🔌"

  print(f"\n--- Node {node_num} Status ---")
  print(f"  Device:       {vendor} {product}")
  print(f"  Serial:       {serial}")
  print(f"  Firmware:     {fw}")
  print(f"  Reachability: {'Online' if target.get('available') else 'Offline'}")
  print(f"  Switch State: {state_str}\n")


async def cmd_toggle(node_id, action):
  try:
    node_num = int(node_id)
  except ValueError:
    print("❌ Error: Node ID must be a number.")
    return

  payload = {
      "message_id": "req_toggle",
      "command": "device_command",
      "args": {
          "node_id": node_num,
          "endpoint_id": 1,
          "cluster_id": 6,
          "command_name": action,
      },
  }
  await send_command(payload)
  print(f"✅ Node {node_num} turned {action.upper()}.")


def main():
  if len(sys.argv) < 2:
    sys.exit(1)

  action = sys.argv[1].lower()

  if action in ["add", "commission"]:
    if len(sys.argv) < 3:
      print("Error: Missing setup code.")
      sys.exit(1)
    asyncio.run(cmd_add(sys.argv[2]))

  elif action in ["del", "delete", "remove"]:
    if len(sys.argv) < 3:
      print("Error: Missing node ID.")
      sys.exit(1)
    asyncio.run(cmd_del(sys.argv[2]))

  elif action in ["list", "ls"]:
    asyncio.run(cmd_list())

  elif action in ["status", "info"]:
    if len(sys.argv) < 3:
      print("Error: Missing node ID.")
      sys.exit(1)
    asyncio.run(cmd_status(sys.argv[2]))

  elif action in ["on", "off"]:
    if len(sys.argv) < 3:
      print("Error: Missing node ID.")
      sys.exit(1)
    asyncio.run(cmd_toggle(sys.argv[2], action))

  else:
    print(f"Unknown action: {action}")


if __name__ == "__main__":
  main()