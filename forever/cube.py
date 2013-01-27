"""
Simple, asynchronous, nonblocking UDP emitter for Cube metrics.
"""

import json
import socket
from datetime import datetime


def emit(event_type, event_data={},
                destination='127.0.0.1', port=1180, **kwargs):
    if not isinstance(event_data, dict):
        event_data = {"value": event_data}
    event = dict(type=event_type, data=event_data)
    event["time"] = kwargs.get("time", datetime.utcnow().isoformat())
    if 'id' in kwargs:
        event["id"] = kwargs.get("id")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
    s.connect((destination, port))
    s.send(json.dumps(event))
    s.close()
