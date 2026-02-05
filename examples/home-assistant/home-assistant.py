#!/usr/bin/env python3
"""
Home Assistant to KDE System Stats Bridge
Fixed WebSocket version
"""

import yaml
import json
import os
import sys
import time
import signal
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import ssl
from websocket import create_connection, WebSocketTimeoutException

# ========== CONFIGURATION ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
LOG_PATH = os.path.join(BASE_DIR, "home-assistant.log")

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

# Graceful shutdown flag
shutdown_flag = threading.Event()

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    shutdown_flag.set()

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ========== UNIT CONVERSION ==========

KDE_ALLOWED_UNITS = {
    "C", "V", "W", "A", "Wh", "%", "rpm", "Hz", "s",
    "dBm", "b/s", "B/s", "B", "Timestamp", "Time", "Ticks", "rate"
}

UNIT_CONVERSION_MAP = {
    # Temperature
    "°C": ("C", 1.0, 1),
    "C": ("C", 1.0, 1),
    "°F": ("C", lambda x: (x - 32) * 5/9, 1),
    "F": ("C", lambda x: (x - 32) * 5/9, 1),
    "K": ("C", lambda x: x - 273.15, 1),
    "kelvin": ("C", lambda x: x - 273.15, 1),
    
    # Power
    "W": ("W", 1.0, 1),
    "watt": ("W", 1.0, 1),
    "kW": ("W", 1000.0, 1),
    "kilowatt": ("W", 1000.0, 1),
    "VA": ("W", 1.0, 1),
    
    # Energy
    "Wh": ("Wh", 1.0, 1),
    "watt hour": ("Wh", 1.0, 1),
    "kWh": ("Wh", 1000.0, 1),
    "kilowatt hour": ("Wh", 1000.0, 1),
    
    # Voltage
    "V": ("V", 1.0, 2),
    "volt": ("V", 1.0, 2),
    "mV": ("V", 0.001, 3),
    "millivolt": ("V", 0.001, 3),
    "kV": ("V", 1000.0, 2),
    "kilovolt": ("V", 1000.0, 2),
    
    # Current
    "A": ("A", 1.0, 2),
    "ampere": ("A", 1.0, 2),
    "mA": ("A", 0.001, 3),
    "milliampere": ("A", 0.001, 3),
    
    # Data/Storage
    "B": ("B", 1.0, 0),
    "byte": ("B", 1.0, 0),
    "bytes": ("B", 1.0, 0),
    "kB": ("B", 1024.0, 0),
    "KB": ("B", 1024.0, 0),
    "kilobyte": ("B", 1024.0, 0),
    "MB": ("B", 1048576.0, 0),
    "megabyte": ("B", 1048576.0, 0),
    "GB": ("B", 1073741824.0, 0),
    "gigabyte": ("B", 1073741824.0, 0),
    
    # Data Rate - Bits per second
    "b/s": ("b/s", 1.0, 0),
    "bps": ("b/s", 1.0, 0),
    "bit/s": ("b/s", 1.0, 0),
    "kbit/s": ("b/s", 1000.0, 0),
    "kbps": ("b/s", 1000.0, 0),
    "kb/s": ("b/s", 1000.0, 0),
    "Kb/s": ("b/s", 1000.0, 0),
    "Mbit/s": ("b/s", 1000000.0, 0),
    "Mbps": ("b/s", 1000000.0, 0),
    "Mb/s": ("b/s", 1000000.0, 0),
    "Gbit/s": ("b/s", 1000000000.0, 0),
    "Gbps": ("b/s", 1000000000.0, 0),
    "Gb/s": ("b/s", 1000000000.0, 0),
    
    # Data Rate - Bytes per second
    "B/s": ("B/s", 1.0, 0),
    "byte/s": ("B/s", 1.0, 0),
    "bytes/s": ("B/s", 1.0, 0),
    "kB/s": ("B/s", 1024.0, 0),
    "KB/s": ("B/s", 1024.0, 0),
    "MB/s": ("B/s", 1048576.0, 0),
    
    # Frequency
    "Hz": ("Hz", 1.0, 1),
    "hertz": ("Hz", 1.0, 1),
    "kHz": ("Hz", 1000.0, 1),
    "kilohertz": ("Hz", 1000.0, 1),
    "MHz": ("Hz", 1000000.0, 1),
    "megahertz": ("Hz", 1000000.0, 1),
    "GHz": ("Hz", 1000000000.0, 1),
    "gigahertz": ("Hz", 1000000000.0, 1),
    
    # Time
    "s": ("s", 1.0, 1),
    "second": ("s", 1.0, 1),
    "seconds": ("s", 1.0, 1),
    "ms": ("s", 0.001, 3),
    "millisecond": ("s", 0.001, 3),
    "milliseconds": ("s", 0.001, 3),
    
    # Percentage
    "%": ("%", 1.0, 1),
    "percent": ("%", 1.0, 1),
    "%RH": ("%", 1.0, 1),
    "rh": ("%", 1.0, 1),
    
    # Signal Strength
    "dBm": ("dBm", 1.0, 1),
    "dB": ("dBm", 1.0, 1),
    
    # Rotation
    "rpm": ("rpm", 1.0, 0),
    "RPM": ("rpm", 1.0, 0),
    
    # Special handling for timestamps
    "timestamp": ("Timestamp", 1.0, 0),
}

def convert_to_kde_unit(raw_value: str, ha_unit: str) -> Tuple[str, str]:
    """Convert Home Assistant value and unit to KDE-compatible format."""
    if not raw_value:
        return "0", "-"
    
    val_str = str(raw_value).replace('\n', ' ').replace('\r', '').strip()
    ha_unit = str(ha_unit).strip() if ha_unit else ""
    
    if val_str.lower() in ["unknown", "unavailable", "none", "null", "off", "false"]:
        return "0", "-"
    if val_str.lower() in ["on", "true"]:
        return "1", "-"
    
    try:
        val = float(val_str)
    except (ValueError, TypeError):
        return val_str, "-"
    
    if ha_unit in UNIT_CONVERSION_MAP:
        kde_unit, conversion, decimals = UNIT_CONVERSION_MAP[ha_unit]
        
        if callable(conversion):
            try:
                converted_val = conversion(val)
            except Exception:
                return f"{val:.{decimals}f}", "-"
        else:
            converted_val = val * conversion
        
        if decimals == 0:
            return str(int(converted_val)), kde_unit
        else:
            return f"{converted_val:.{decimals}f}", kde_unit
    
    if ha_unit == "" and val_str.isdigit() and len(val_str) == 10:
        try:
            ts = int(val_str)
            if 1000000000 < ts < 2000000000:
                return val_str, "Timestamp"
        except:
            pass
    
    try:
        return f"{float(val_str):.2f}", "-"
    except:
        return val_str, "-"

# ========== CONFIG LOADING ==========

def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    try:
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)
        
        required_keys = ['home_assistant', 'sensors']
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required config key: {key}")
        
        ha_config = config['home_assistant']
        ha_required = ['host', 'token']
        for key in ha_required:
            if key not in ha_config:
                raise ValueError(f"Missing required home_assistant key: {key}")
        
        logger.info(f"Loaded config with {len(config['sensors'])} sensors")
        return config
        
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {
            'home_assistant': {
                'host': 'localhost',
                'port': 8123,
                'token': 'demo'
            },
            'sensors': {
                'demo': {
                    'entity': 'sensor.demo',
                    'name': 'Demo Sensor'
                }
            }
        }

# ========== HOME ASSISTANT CLIENT ==========

class HAClient:
    """WebSocket client for Home Assistant."""
    
    def __init__(self, host: str, port: int, token: str, entities: list, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.token = token
        self.entities = entities
        self.use_ssl = use_ssl
        self.ws = None
        self.states = {e: {"state": "0", "unit": "", "last_update": 0} for e in entities}
        self.lock = threading.Lock()
        self.connected = False
        self.reconnect_delay = 5
        self.last_reconnect = 0
        self.initial_states_ready = threading.Event()
        self.connection_lock = threading.Lock()
        
    def _get_url(self) -> str:
        """Get WebSocket URL."""
        proto = "wss" if self.use_ssl else "ws"
        return f"{proto}://{self.host}:{self.port}/api/websocket"
    
    def connect(self) -> bool:
        """Connect to Home Assistant WebSocket API."""
        with self.connection_lock:
            if self.connected:
                return True
                
            if time.time() - self.last_reconnect < self.reconnect_delay:
                return False
                
            try:
                sslopt = {"cert_reqs": ssl.CERT_NONE} if self.use_ssl else {}
                self.ws = create_connection(self._get_url(), timeout=15, sslopt=sslopt)
                
                auth_required = json.loads(self.ws.recv())
                if auth_required.get("type") != "auth_required":
                    return False
                
                self.ws.send(json.dumps({"type": "auth", "access_token": self.token}))
                auth_response = json.loads(self.ws.recv())
                if auth_response.get("type") != "auth_ok":
                    return False
                
                self.ws.send(json.dumps({"id": 1, "type": "get_states"}))
                self.ws.send(json.dumps({
                    "id": 2, 
                    "type": "subscribe_events", 
                    "event_type": "state_changed"
                }))
                
                self.connected = True
                self.last_reconnect = time.time()
                logger.info(f"Connected to Home Assistant")
                
                threading.Thread(target=self._listen, daemon=True).start()
                return True
                
            except Exception as e:
                logger.error(f"Failed to connect: {e}")
                self.connected = False
                self.last_reconnect = time.time()
                return False
    
    def _listen(self):
        """Listen for WebSocket messages."""
        while not shutdown_flag.is_set() and self.connected:
            try:
                msg = json.loads(self.ws.recv())
                
                if msg.get("id") == 1:
                    for state in msg.get("result", []):
                        self._update_state(state)
                    self.initial_states_ready.set()
                    
                elif msg.get("type") == "event" and msg["event"]["event_type"] == "state_changed":
                    new_state = msg["event"]["data"].get("new_state")
                    if new_state:
                        self._update_state(new_state)
                        
            except WebSocketTimeoutException:
                continue
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.connected = False
                self.initial_states_ready.clear()
                break
        
        if not shutdown_flag.is_set():
            time.sleep(self.reconnect_delay)
            self.connect()
    
    def _update_state(self, state_data: dict):
        """Update internal state cache."""
        entity_id = state_data.get("entity_id")
        if entity_id not in self.entities:
            return
            
        with self.lock:
            self.states[entity_id] = {
                "state": state_data.get("state", "0"),
                "unit": state_data.get("attributes", {}).get("unit_of_measurement", ""),
                "last_update": time.time()
            }
    
    def get_state(self, entity_id: str) -> Dict[str, Any]:
        """Get current state for an entity."""
        with self.lock:
            return self.states.get(entity_id, {"state": "0", "unit": "", "last_update": 0})
    
    def wait_for_initial_states(self, timeout: float = 30.0) -> bool:
        """Wait for initial states to be loaded."""
        return self.initial_states_ready.wait(timeout)
    
    def disconnect(self):
        """Disconnect from Home Assistant."""
        self.connected = False
        self.initial_states_ready.clear()
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

# ========== MAIN APPLICATION ==========

def main():
    """Main application loop."""
    config = load_config()
    ha_config = config['home_assistant']
    
    # Parse sensors config - KEEP YOUR EXISTING STRUCTURE
    sensors = {}
    sensor_entities = []
    for sensor_id, sensor_config in config['sensors'].items():
        if isinstance(sensor_config, str):
            sensors[sensor_id] = {"entity": sensor_config}
            sensor_entities.append(sensor_config)
        else:
            sensors[sensor_id] = sensor_config
            sensor_entities.append(sensor_config['entity'])
    
    logger.info(f"Monitoring {len(sensor_entities)} entities")
    
    # Create HA client
    client = HAClient(
        host=ha_config['host'],
        port=ha_config.get('port', 8123),
        token=ha_config['token'],
        entities=sensor_entities,
        use_ssl=ha_config.get('ssl', True)
    )
    
    # Connect to HA BEFORE starting main loop
    logger.info("Connecting to Home Assistant...")
    if client.connect():
        logger.info("Connected, waiting for initial states...")
        client.wait_for_initial_states(timeout=30.0)
    else:
        logger.warning("Failed to connect, running in offline mode")
    
    # Main protocol loop
    logger.info("Ready for KSystemStats queries")
    
    import select
    
    while not shutdown_flag.is_set():
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            
            if ready:
                line = sys.stdin.readline()
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split("\t")
                if not parts:
                    continue
                
                cmd = parts[0]
                
                # Handle "?" command - list sensors - FIXED TO RETURN CONFIG KEYS
                if cmd == "?":
                    # Return the sensor IDs from your config (blue_mage_battery, etc.)
                    print("\t".join(config['sensors'].keys()))
                    sys.stdout.flush()
                    continue
                
                # Handle sensor-specific commands
                if cmd in sensors:
                    sensor_config = sensors[cmd]
                    entity_id = sensor_config['entity']
                    
                    state_data = client.get_state(entity_id)
                    ha_unit = sensor_config.get('unit') or state_data['unit']
                    
                    kde_value, kde_unit = convert_to_kde_unit(
                        state_data['state'], 
                        ha_unit
                    )
                    
                    if len(parts) > 1:
                        subcmd = parts[1]
                        
                        if subcmd == "value":
                            print(kde_value)
                        elif subcmd == "unit":
                            print(kde_unit)
                        elif subcmd == "name":
                            print(sensor_config.get('name', cmd))
                        elif subcmd == "short_name":
                            print(sensor_config.get('short_name', sensor_config.get('name', cmd)))
                        elif subcmd == "prefix":
                            print(sensor_config.get('prefix', ""))
                        elif subcmd == "description":
                            print(sensor_config.get('description', ""))
                        elif subcmd == "min":
                            print(sensor_config.get('min', "0"))
                        elif subcmd == "max":
                            print(sensor_config.get('max', "100"))
                        elif subcmd == "initial_value":
                            print(sensor_config.get('initial_value', kde_value))
                        elif subcmd == "variant_type":
                            print(sensor_config.get('variant_type', "double"))
                        else:
                            print()
                    else:
                        print()
                    
                    sys.stdout.flush()
                    
                else:
                    print()
                    sys.stdout.flush()
            
            if not client.connected and time.time() - client.last_reconnect > client.reconnect_delay:
                client.connect()
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Error: {e}")
            print()
            sys.stdout.flush()
            time.sleep(1)
    
    logger.info("Shutting down...")
    client.disconnect()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)
