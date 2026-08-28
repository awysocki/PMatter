import asyncio
import json
import websockets

MATTER_URI = "ws://192.168.2.88:5580/ws"
NODE_ID = 1  # Tapo S505 Node ID


async def listen_for_events(ws):
  """Handles real-time pushed events and direct command responses."""
  try:
    async for message in ws:
      data = json.loads(message)
      event_type = data.get("event")

      # 1. Catch live push updates (app / wall button toggles)
      if event_type == "attribute_updated":
        evt_data = data.get("data", [])
        # Expecting array format: [node_id, attribute_path, value]
        if len(evt_data) >= 3:
          node_id, attr_path, value = evt_data[0], evt_data[1], evt_data[2]

          if node_id == NODE_ID and attr_path == "1/6/0":
            state_str = "ON " if value else "OFF "
            print(
                f"\n[LIVE EVENT] Tapo Switch (Node {NODE_ID}) is now:"
                f" {state_str}"
            )
            print("Command (on/off/status/quit): ", end="", flush=True)

      # 2. Catch direct command responses
      elif "message_id" in data:
        msg_id = data.get("message_id")

        if msg_id.startswith("status_"):
          result = data.get("result", [])
          if result:
            node = result[0]
            attributes = node.get("attributes", {})
            is_on = attributes.get("1/6/0")
            print(
                f"\n[STATUS RESPONSE] Node {NODE_ID} is currently:"
                f" {'ON ' if is_on else 'OFF '}"
            )
          print("Command (on/off/status/quit): ", end="", flush=True)

        elif msg_id.startswith("cmd_"):
          print("\n[COMMAND ACK] Command sent successfully.")
          print("Command (on/off/status/quit): ", end="", flush=True)

  except asyncio.CancelledError:
    pass
  except Exception as e:
    print(f"\n[Listener Error] {e}")


async def main():
  print(f"Connecting to Matter Server at {MATTER_URI}...")

  async with websockets.connect(MATTER_URI) as ws:
    # Read initial server handshake payload
    await ws.recv()

    # Subscribe to live attribute update events across the fabric
    await ws.send(
        json.dumps({"message_id": "sub_1", "command": "start_listening"})
    )

    print("Connected! Active event subscription established.\n")

    listener_task = asyncio.create_task(listen_for_events(ws))

    print("=" * 50)
    print("TAPO S505 MATTER TESTER")
    print("Toggle in Tapo App or on wall to test dynamic live updates.")
    print("=" * 50 + "\n")

    msg_counter = 1
    loop = asyncio.get_running_loop()

    while True:
      user_input = await loop.run_in_executor(
          None, input, "Command (on/off/status/quit): "
      )
      cmd = user_input.strip().lower()

      if cmd == "quit":
        listener_task.cancel()
        break

      elif cmd in ["on", "off"]:
        msg_id = f"cmd_{msg_counter}"
        payload = {
            "message_id": msg_id,
            "command": "device_command",
            "args": {
                "node_id": NODE_ID,
                "endpoint_id": 1,
                "cluster_id": 6,
                "command_name": cmd,
            },
        }
        await ws.send(json.dumps(payload))
        msg_counter += 1

      elif cmd == "status":
        msg_id = f"status_{msg_counter}"
        payload = {"message_id": msg_id, "command": "get_nodes"}
        await ws.send(json.dumps(payload))
        msg_counter += 1

    await listener_task


if __name__ == "__main__":
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    print("\nExiting...")