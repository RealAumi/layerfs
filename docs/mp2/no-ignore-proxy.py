#!/usr/bin/env python3
"""Count actual Store-link ciphertext bytes; no replay or fault injection."""
import json
import os
import selectors
import socket
import threading

counts = {'to_store_bytes': 0, 'from_store_bytes': 0, 'connections': 0}
lock = threading.Lock()


def relay(client):
    server = socket.create_connection((os.environ['CXN_SERVER'], 7800), timeout=5)
    server.settimeout(None)
    for endpoint in (client, server):
        endpoint.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    selector = selectors.DefaultSelector()
    selector.register(client, selectors.EVENT_READ, (server, 'to_store_bytes'))
    selector.register(server, selectors.EVENT_READ, (client, 'from_store_bytes'))
    try:
        while True:
            for key, _ in selector.select():
                data = key.fileobj.recv(65536)
                if not data:
                    return
                target, counter = key.data
                target.sendall(data)
                with lock:
                    counts[counter] += len(data)
    finally:
        selector.close()
        client.close()
        server.close()


def observations():
    listener = socket.socket(socket.AF_UNIX)
    listener.bind('/state/proxy.sock')
    listener.listen()
    while True:
        client, _ = listener.accept()
        with client, lock:
            client.sendall(json.dumps(counts).encode())


threading.Thread(target=observations, daemon=True).start()
listener = socket.socket()
listener.bind(('127.0.0.1', 7900))
listener.listen()
print('PROXY_READY', flush=True)
while True:
    client, _ = listener.accept()
    with lock:
        counts['connections'] += 1
    threading.Thread(target=relay, args=(client,), daemon=True).start()
