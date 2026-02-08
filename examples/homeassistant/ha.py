#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Bram-diederik
# SPDX-FileCopyrightText: 2026 KerJoe <2002morozik@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

# See https://github.com/Bram-diederik/ksystemstats_scripts/tree/master/examples/home-assistant for a more complete implementation

import yaml
import requests
import os
import sys

def get_ha_state(entity_id, url, token):
    """
    Fetch the state from Home Assistant.
    Returns the state and attributes for potential future use.
    """
    api_url = f"{url.rstrip('/')}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(api_url, headers=headers, timeout=2)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# Get absolute config path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
try:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    ha_url = config['home_assistant']['url']
    ha_token = config['home_assistant']['token']
    sensor_map = config.get('sensors', {})
except Exception:
    print(f"Failure parsing '{CONFIG_PATH}'")
    sys.exit(1)

while True:
    try:
        req = input().strip().split("\t")
        command = req[0]

        # 1. Metadata request
        if command == "?":
            # Print all keys from YAML separated by tabs
            print("\t".join(sensor_map.keys()))

        # 2. Sensor specific requests
        elif command in sensor_map:
            entity_id = sensor_map[command]['entity']
            sub_req = req[1]

            if sub_req == "value":
                data = get_ha_state(entity_id, ha_url, ha_token)
                print(data['state'] if data else "")

            elif sub_req == "unit":
                data = get_ha_state(entity_id, ha_url, ha_token)
                # Fetch unit from HA attributes if available
                if data and 'unit_of_measurement' in data['attributes']:
                    print(data['attributes']['unit_of_measurement'])
                else:
                    print()

            elif sub_req == "name":
                data = get_ha_state(entity_id, ha_url, ha_token)
                print(data['attributes']['friendly_name'] if data else "")

            elif sub_req == "min":
                print(sensor_map[command]['min'] if 'min' in sensor_map[command] else "")

            elif sub_req == "max":
                print(sensor_map[command]['max'] if 'max' in sensor_map[command] else "")

            elif sub_req == "variant_type":
                data = get_ha_state(entity_id, ha_url, ha_token)
                if data:
                    try:
                        # Attempt number conversion
                        str(float(data['state']))
                        print('double')
                    except ValueError:
                        print('QString')
                else:
                    print()

            else:
                print()

        else:
            print()

    except Exception as e:
        # Errors to stderr to keep stdout clean for ksystemstats
        sys.stderr.write(f"Error: {e}\n")
        print()
