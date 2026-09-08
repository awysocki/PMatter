import asyncio
import json
import os
import sys
import websockets

DEFAULT_MATTER_URI = os.environ.get(
  "MATTER_SERVER_URI", "ws://localhost:5580/ws"
)


def parse_args(argv):
  """Accept the URI and/or a node_id filter in either order.

  A bare numeric argument is treated as a node_id filter; anything
  containing "://" is treated as the server URI. With no node_id, every
  device's events are printed; with one, only that node's are.
  """
  uri = DEFAULT_MATTER_URI
  node_id = None
  for arg in argv:
    if "://" in arg:
      uri = arg
    elif arg.lstrip("-").isdigit():
      node_id = int(arg)
    else:
      print(f"Ignoring unrecognized argument: {arg}", file=sys.stderr)
  return uri, node_id


def message_node_id(data):
  """Return the node_id a packet is about, or None if it isn't per-node."""
  event_type = data.get("event")
  if event_type == "node_event":
    return data.get("data", {}).get("node_id")
  if event_type == "attribute_updated":
    values = data.get("data", [])
    if values:
      return values[0]
  return None


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
  matter_uri, node_id_filter = parse_args(sys.argv[1:])
  print(f"Connecting to {matter_uri}...")
  if node_id_filter is not None:
    print(f"Filtering output to node_id={node_id_filter}")
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
      if node_id_filter is not None:
        try:
          data = json.loads(msg)
        except (TypeError, ValueError):
          data = {}
        packet_node_id = message_node_id(data)
        if packet_node_id is not None and packet_node_id != node_id_filter:
          continue
      print(compact_message(msg), flush=True)


if __name__ == "__main__":
  try:
    asyncio.run(debug_events())
  except KeyboardInterrupt:
    print("\nStopped.")
