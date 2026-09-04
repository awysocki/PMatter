import asyncio
import json
import os
import sys
import websockets

DEFAULT_MATTER_URI = os.environ.get(
  "MATTER_SERVER_URI", "ws://localhost:5580/ws"
)


def compact_message(message):
  """Return one short line for the most useful parts of a server packet."""
  try:
    data = json.loads(message)
  except (TypeError, ValueError):
    return str(message).replace("\n", " ")[:240]

  event_type = data.get("event")
  if event_type == "node_event":
    event = data.get("data", {})
    return (
        "EVENT node={node} ep={endpoint} cluster={cluster} event={event_id} data={data}"
        .format(
            node=event.get("node_id", "?"),
            endpoint=event.get("endpoint_id", "?"),
            cluster=event.get("cluster_id", "?"),
            event_id=event.get("event_id", "?"),
            data=event.get("data", {}),
        )
    )
  if event_type == "attribute_updated":
    values = data.get("data", [])
    return f"ATTR {values}"
  if event_type:
    return f"EVENT {event_type}"
  if "message_id" in data:
    result = data.get("result")
    if isinstance(result, list):
      return f"RESPONSE {data['message_id']} items={len(result)}"
    return f"RESPONSE {data['message_id']}"
  return "PACKET " + json.dumps(data, separators=(",", ":"))[:220]


async def debug_events():
  matter_uri = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MATTER_URI
  print(f"Connecting to {matter_uri}...")
  async with websockets.connect(matter_uri) as ws:
    handshake = await ws.recv()
    print(f"HANDSHAKE {compact_message(handshake)}", flush=True)

    # 2. Subscribe to event stream
    await ws.send(
        json.dumps({"message_id": "sub_events", "command": "start_listening"})
    )

    print("LISTENING - press a button (Ctrl+C to stop)", flush=True)

    while True:
      msg = await ws.recv()
      print(compact_message(msg), flush=True)


if __name__ == "__main__":
  try:
    asyncio.run(debug_events())
  except KeyboardInterrupt:
    print("\nStopped.")
