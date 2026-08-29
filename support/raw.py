import asyncio
import json
import websockets

MATTER_URI = "ws://localhost:5580/ws"


async def debug_events():
  print(f"Connecting to {MATTER_URI}...")
  async with websockets.connect(MATTER_URI) as ws:
    # 1. Server info handshake
    handshake = await ws.recv()
    print(f"\n[SERVER HANDSHAKE]\n{handshake}\n")

    # 2. Subscribe to event stream
    await ws.send(
        json.dumps({"message_id": "sub_events", "command": "start_listening"})
    )

    print("=" * 60)
    print("LISTENING FOR RAW MATTER SERVER EVENTS")
    print("Now open the TAPO APP and toggle the switch on/off...")
    print("=" * 60 + "\n")

    while True:
      msg = await ws.recv()
      data = json.loads(msg)

      # Filter out static node dump on initial connect if too noisy
      if data.get("message_id") == "sub_events":
        print("[SUBSCRIBED SUCCESSFULLY] Initial node snapshot received.")
        continue

      print(f"[RAW INCOMING EVENT]\n{json.dumps(data, indent=2)}\n")


if __name__ == "__main__":
  try:
    asyncio.run(debug_events())
  except KeyboardInterrupt:
    print("\nStopped.")
