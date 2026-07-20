import random
import time
from datetime import datetime, UTC

import requests

LOKI_URL = "http://loki:3100/loki/api/v1/push"

SATELLITES = [
    "Kosmos-2553",
    "Meteor-M3",
    "Luch-5X",
    "GLONASS-K2",
]

EVENTS = [
    ("INFO", "Telemetry received"),
    ("INFO", "Position updated"),
    ("INFO", "Battery status updated"),
    ("WARNING", "Battery below 30%"),
    ("WARNING", "High onboard temperature"),
    ("WARNING", "Signal delay detected"),
    ("ERROR", "Telemetry checksum mismatch"),
    ("ERROR", "GPS synchronization failed"),
    ("ERROR", "Communication lost"),
]

session = requests.Session()

for _ in range(1000):
    satellite = random.choice(SATELLITES)
    level, message = random.choice(EVENTS)

    payload = {
        "streams": [
            {
                "stream": {
                    "job": "satellites",
                    "satellite": satellite,
                    "level": level,
                },
                "values": [
                    [
                        str(time.time_ns()),
                        f"{datetime.now(UTC).isoformat()} {message}",
                    ]
                ],
            }
        ]
    }

    r = session.post(LOKI_URL, json=payload)

    if r.status_code != 204:
        print("ERROR:", r.status_code)
        print(r.text)
        break

print("Done")