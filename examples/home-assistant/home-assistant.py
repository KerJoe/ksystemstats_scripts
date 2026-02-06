#!/usr/bin/env python3
"""
Home Assistant to KDE System Stats Bridge
Fixed for proper string handling - no units for strings
Added SSL certificate options
Fixed connection issues
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

# Default SSL paths for Debian/Ubuntu
DEFAULT_SSL_CERT_PATH = "/etc/ssl/certs/ca-certificates.crt"
ALTERNATIVE_SSL_PATHS = [
    "/etc/ssl/certs/ca-bundle.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/cert.pem",
]

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

# ========== SSL HELPER FUNCTIONS ==========

def find_default_cert():
    """Find the default SSL certificate bundle on the system."""
    # Check default Debian/Ubuntu path
    if os.path.exists(DEFAULT_SSL_CERT_PATH):
        return DEFAULT_SSL_CERT_PATH

    # Check alternative paths
    for path in ALTERNATIVE_SSL_PATHS:
        if os.path.exists(path):
            return path

    # Check if certifi is available (Python package)
    try:
        import certifi
        return certifi.where()
    except ImportError:
        pass

    # Last resort: check common locations
    common_locations = [
        "/usr/lib/ssl/certs/ca-certificates.crt",
        "/usr/local/ssl/certs/ca-certificates.crt",
        "/opt/ssl/certs/ca-certificates.crt",
    ]

    for location in common_locations:
        if os.path.exists(location):
            return location

    return None

def create_ssl_context(ssl_config: Dict[str, Any]) -> Optional[ssl.SSLContext]:
    """Create SSL context based on configuration."""
    if not ssl_config.get('enabled', True):
        return None

    verify = ssl_config.get('verify', True)
    cert_path = ssl_config.get('cert_path')

    # If verification is disabled, return context with no verification
    if not verify:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    # If specific cert path is provided
    if cert_path:
        if os.path.exists(cert_path):
            context = ssl.create_default_context(cafile=cert_path)
            logger.info(f"Using custom SSL certificate: {cert_path}")
            return context
        else:
            logger.warning(f"Custom SSL certificate not found: {cert_path}. Trying defaults...")

    # Try to find default certificate
    default_cert = find_default_cert()
    if default_cert:
        context = ssl.create_default_context(cafile=default_cert)
        logger.info(f"Using default SSL certificate: {default_cert}")
        return context

    # No certificate found - create context without verification
    logger.warning("No SSL certificate found, disabling verification")
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context

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

def get_unit_for_conversion(sensor_config: Dict[str, Any], ha_unit: str) -> str:
    """Determine which unit to use for conversion."""
    if 'unit' in sensor_config:
        return sensor_config['unit']
    elif ha_unit:
        return ha_unit
    else:
        return ""

def is_string_sensor(sensor_config: Dict[str, Any]) -> bool:
    """Check if sensor is configured as a string sensor."""
    variant_type = sensor_config.get('variant_type', '').lower()
    return variant_type in ['string', 'qstring']

def convert_to_kde_unit(raw_value: str, ha_unit: str, sensor_config: Dict[str, Any] = None) -> Tuple[str, str]:
    """Convert Home Assistant value and unit to KDE-compatible format.
    Returns: (value, unit)
    """
    if raw_value is None:
        return "0", ""

    val_str = str(raw_value).replace('\n', ' ').replace('\r', '').strip()
    ha_unit = str(ha_unit).strip() if ha_unit else ""

    # Check if this is a string sensor - ALWAYS return the string value as-is
    if sensor_config and is_string_sensor(sensor_config):
        # String sensor - return string value as-is, unit is empty string
        return val_str, ""

    # For non-string sensors, try to handle numeric values
    # First check if it's a known boolean state
    if val_str.lower() in ["unknown", "unavailable", "none", "null"]:
        return "0", "-"
    if val_str.lower() in ["off", "false"]:
        return "0", "-"
    if val_str.lower() in ["on", "true"]:
        return "1", "-"

    # Try to parse as number
    try:
        val = float(val_str)
    except (ValueError, TypeError):
        # Not a number - return as-is with "-" unit
        return val_str, "-"

    # We have a numeric value - apply unit conversion if needed
    if ha_unit and ha_unit in UNIT_CONVERSION_MAP:
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

    # Special handling for timestamps
    if ha_unit == "" and val_str.isdigit() and len(val_str) == 10:
        try:
            ts = int(val_str)
            if 1000000000 < ts < 2000000000:
                return val_str, "Timestamp"
        except:
            pass

    # If no conversion needed or unit is already KDE-compatible
    if ha_unit and ha_unit in KDE_ALLOWED_UNITS:
        try:
            if ha_unit in ["B", "b/s", "B/s"]:
                return str(int(val)), ha_unit
            else:
                return f"{val:.2f}", ha_unit
        except:
            return val_str, ha_unit

    # Numeric value without unit or with unknown unit
    return f"{val:.2f}", "-"

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

        # Set default SSL configuration if not specified
        if 'ssl' not in ha_config:
            ha_config['ssl'] = {
                'enabled': True,
                'verify': True
            }
        elif isinstance(ha_config['ssl'], bool):
            # Backward compatibility: ssl: true/false
            ha_config['ssl'] = {
                'enabled': ha_config['ssl'],
                'verify': ha_config['ssl']
            }
        elif isinstance(ha_config['ssl'], dict):
            # Ensure all SSL options are set
            ha_config['ssl'].setdefault('enabled', True)
            ha_config['ssl'].setdefault('verify', True)
            ha_config['ssl'].setdefault('cert_path', None)
        else:
            raise ValueError("SSL configuration must be boolean or dictionary")

        logger.info(f"Loaded config with {len(config['sensors'])} sensors")
        logger.info(f"SSL configuration: {ha_config['ssl']}")

        return config

    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {
            'home_assistant': {
                'host': 'localhost',
                'port': 8123,
                'token': 'demo',
                'ssl': {
                    'enabled': True,
                    'verify': True,
                    'cert_path': None
                }
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

    def __init__(self, host: str, port: int, token: str, entities: list, ssl_config: Dict[str, Any]):
        self.host = host
        self.port = port
        self.token = token
        self.entities = entities
        self.ssl_config = ssl_config
        self.ssl_context = create_ssl_context(ssl_config)
        self.ws = None
        self.states = {e: {"state": "0", "unit": "", "last_update": 0} for e in entities}
        self.lock = threading.Lock()
        self.connected = False
        self.reconnect_delay = 5
        self.last_reconnect = 0
        self.initial_states_ready = threading.Event()
        self.connection_lock = threading.Lock()
        self.connect_attempts = 0
        self.max_connect_attempts = 10

    def _get_url(self) -> str:
        """Get WebSocket URL."""
        use_ssl = self.ssl_config.get('enabled', True)
        proto = "wss" if use_ssl else "ws"
        return f"{proto}://{self.host}:{self.port}/api/websocket"

    def connect(self) -> bool:
        """Connect to Home Assistant WebSocket API."""
        with self.connection_lock:
            if self.connected:
                return True

            if time.time() - self.last_reconnect < self.reconnect_delay:
                return False

            try:
                # Prepare SSL options
                sslopt = {}
                use_ssl = self.ssl_config.get('enabled', True)

                if use_ssl and self.ssl_context:
                    sslopt['sslopt'] = {"context": self.ssl_context}

                # Log SSL configuration
                verify = self.ssl_config.get('verify', True)
                logger.info(f"Connecting to {self._get_url()} with SSL verify={verify}, context={self.ssl_context is not None}")

                self.ws = create_connection(self._get_url(), timeout=15, **sslopt)

                auth_required = json.loads(self.ws.recv())
                if auth_required.get("type") != "auth_required":
                    logger.error(f"Unexpected response: {auth_required}")
                    return False

                self.ws.send(json.dumps({"type": "auth", "access_token": self.token}))
                auth_response = json.loads(self.ws.recv())
                if auth_response.get("type") != "auth_ok":
                    logger.error(f"Authentication failed: {auth_response}")
                    return False

                # Get initial states
                self.ws.send(json.dumps({"id": 1, "type": "get_states"}))

                # Subscribe to state changes
                self.ws.send(json.dumps({
                    "id": 2,
                    "type": "subscribe_events",
                    "event_type": "state_changed"
                }))

                self.connected = True
                self.connect_attempts = 0
                self.last_reconnect = time.time()
                logger.info(f"Connected to Home Assistant at {self.host}:{self.port}")

                threading.Thread(target=self._listen, daemon=True).start()
                return True

            except Exception as e:
                self.connect_attempts += 1
                logger.error(f"Failed to connect (attempt {self.connect_attempts}/{self.max_connect_attempts}): {e}")
                self.connected = False
                self.last_reconnect = time.time()

                # Increase reconnect delay with each failed attempt
                self.reconnect_delay = min(30, 5 * self.connect_attempts)
                logger.info(f"Next reconnect attempt in {self.reconnect_delay} seconds")

                return False

    def _listen(self):
        """Listen for WebSocket messages."""
        while not shutdown_flag.is_set() and self.connected:
            try:
                msg = json.loads(self.ws.recv())

                if msg.get("id") == 1:
                    logger.info(f"Received initial states for {len(msg.get('result', []))} entities")
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
            logger.info("Attempting to reconnect...")
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
            logger.debug(f"Updated {entity_id}: {state_data.get('state', '0')} {state_data.get('attributes', {}).get('unit_of_measurement', '')}")

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

    # Parse sensors config
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
        ssl_config=ha_config['ssl']
    )

    # Initial connection attempt
    logger.info("Attempting initial connection to Home Assistant...")
    connection_successful = client.connect()

    if connection_successful:
        logger.info("Waiting for initial states...")
        if client.wait_for_initial_states(timeout=30.0):
            logger.info("Initial states loaded successfully")
        else:
            logger.warning("Timeout waiting for initial states")
    else:
        logger.warning("Initial connection failed. Will retry in background.")

    # Log initial states for debugging
    logger.info("Initial sensor states:")
    for sensor_id, sensor_config in sensors.items():
        entity_id = sensor_config['entity']
        state_data = client.get_state(entity_id)
        logger.info(f"  {sensor_id} ({entity_id}): {state_data['state']} {state_data['unit']}")

    # Main protocol loop
    logger.info("Ready for KSystemStats queries")

    import select

    last_connection_check = 0
    connection_check_interval = 10  # Check connection every 10 seconds

    while not shutdown_flag.is_set():
        try:
            # Check connection periodically
            current_time = time.time()
            if current_time - last_connection_check > connection_check_interval:
                if not client.connected and current_time - client.last_reconnect > client.reconnect_delay:
                    logger.info("Attempting to reconnect...")
                    client.connect()
                last_connection_check = current_time

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

                # Handle "?" command - list sensors
                if cmd == "?":
                    print("\t".join(config['sensors'].keys()))
                    sys.stdout.flush()
                    continue

                # Handle sensor-specific commands
                if cmd in sensors:
                    sensor_config = sensors[cmd]
                    entity_id = sensor_config['entity']

                    state_data = client.get_state(entity_id)

                    # Log the raw data for debugging
                    logger.debug(f"Query: {cmd}, Entity: {entity_id}, Raw state: {state_data['state']}, Raw unit: {state_data['unit']}")

                    # Determine which Home Assistant unit to use
                    ha_unit = get_unit_for_conversion(sensor_config, state_data['unit'])

                    # Convert to KDE format
                    kde_value, kde_unit = convert_to_kde_unit(state_data['state'], ha_unit, sensor_config)

                    logger.debug(f"Converted: {kde_value} {kde_unit}")

                    if len(parts) > 1:
                        subcmd = parts[1]

                        if subcmd == "value":
                            print(kde_value)
                        elif subcmd == "unit":
                            # For string sensors, return empty string (no unit)
                            if is_string_sensor(sensor_config):
                                print("")
                            else:
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
                            # Use configured variant_type or default based on sensor type
                            variant_type = sensor_config.get('variant_type', '')
                            if not variant_type:
                                # Auto-detect: if string sensor, use QString
                                if is_string_sensor(sensor_config):
                                    variant_type = "QString"
                                else:
                                    variant_type = "double"
                            print(variant_type)
                        else:
                            print()
                    else:
                        print()

                    sys.stdout.flush()

                else:
                    print()
                    sys.stdout.flush()

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
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
