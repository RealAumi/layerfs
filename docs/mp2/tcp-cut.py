#!/usr/bin/env python3
"""External fault probe; never part of the daemon or Store protocol."""
import json, pathlib, selectors, socket, threading, time
root = pathlib.Path('/state')
listener = socket.socket(); listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(('127.0.0.1', 7900)); listener.listen()
print('PROXY_READY', flush=True)
def relay(client, number):
    server = socket.create_connection(('store', 7800), timeout=5)
    server.settimeout(None)
    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    server.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    selector = selectors.DefaultSelector()
    selector.register(client, selectors.EVENT_READ, server)
    selector.register(server, selectors.EVENT_READ, client)
    armed_bytes = 0
    try:
        while True:
            for key, _ in selector.select(timeout=1):
                data = key.fileobj.recv(65536)
                if not data: return
                flag = root / ('cut-read' if number == 1 else 'cut-write')
                if key.fileobj is client and flag.exists():
                    armed_bytes += len(data)
                    threshold = 1 if number == 1 else 200000
                    if armed_bytes >= threshold:
                        with (root / 'cut-events.jsonl').open('a') as out:
                            out.write(json.dumps(dict(connection=number, bytes=armed_bytes, time=time.time()))+'\n')
                        return
                key.data.sendall(data)
    finally:
        selector.close(); client.close(); server.close()
number = 0
while True:
    client, _ = listener.accept(); number += 1
    with (root / 'connections.jsonl').open('a') as out: out.write(json.dumps(dict(connection=number))+'\n')
    threading.Thread(target=relay, args=(client, number), daemon=True).start()
