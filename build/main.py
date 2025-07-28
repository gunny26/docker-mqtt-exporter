#!/usr/bin/python3
"""
MQTT to Prometheus Exporter
Reads IoT data from MQTT broker and exports metrics for Prometheus.
"""
import json
import logging
import os
import signal
import sys
import time
from typing import Optional

import paho.mqtt.client as mqtt
from prometheus_client import start_http_server, Gauge, Counter


# Configuration from environment
MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))  # Fixed typo: 1833 -> 1883
MQTT_CLIENT_ID = os.environ["MQTT_CLIENT_ID"]
MQTT_CLIENT_SECRET = os.environ["MQTT_CLIENT_SECRET"]
MQTT_KEEPALIVE = int(os.environ.get("MQTT_KEEPALIVE", "60"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "homie/#")
DEBUG_LEVEL = os.environ.get("DEBUG_LEVEL", "INFO")
PROM_EXPORTER_PORT = int(os.environ.get("PROMETHEUS_PORT", "9100"))

# Setup logging
logging.basicConfig(
    level=getattr(logging, DEBUG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
running = True
client = None


class CounterWithSet(Counter):
    """Counter class with set method for total energy values"""
    
    def set(self, value: float) -> None:
        """Set counter to the given value (for total counters)"""
        self._raise_if_not_observable()
        self._value.set(float(value))


# Prometheus metrics
METRICS = {
    "temperature": Gauge('homie_property_temperature', 'Temperature in °C', ["device", "node"]),
    "humidity": Gauge('homie_property_humidity', 'Humidity in %', ["device", "node"]),
    "light": Gauge("homie_property_light", "Light strength in lumen", ["device", "node"]),
    "energy5": Gauge("homie_property_energy5", "Energy consumption last 5min in Wh", ["device", "node"]),
    "energyhour": Gauge("homie_property_energyhour", "Energy consumption last hour in Wh", ["device", "node"]),
    "totalenergy": Gauge("homie_property_totalenergy", "Energy consumption total in Wh", ["device", "node"]),
    "energy": CounterWithSet("homie_property_energy", "S0 impulses total", ["device", "node"]),
}

# Additional monitoring metrics
mqtt_messages_received = Counter('mqtt_messages_received_total', 'Total MQTT messages received')
mqtt_messages_processed = Counter('mqtt_messages_processed_total', 'Total MQTT messages processed successfully')
mqtt_messages_errors = Counter('mqtt_messages_errors_total', 'Total MQTT message processing errors')
mqtt_connection_status = Gauge('mqtt_connection_status', 'MQTT connection status (1=connected, 0=disconnected)')


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global running, client
    logger.info(f"Received signal {signum}, shutting down...")
    running = False
    if client:
        client.disconnect()


def on_connect(client, userdata, flags, rc):
    """Callback for MQTT connection"""
    if rc == 0:
        logger.info("Successfully connected to MQTT broker")
        mqtt_connection_status.set(1)
        
        # Subscribe to topic
        logger.info(f"Subscribing to topic: {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC)
    else:
        logger.error(f"Failed to connect to MQTT broker, return code: {rc}")
        mqtt_connection_status.set(0)


def on_disconnect(client, userdata, rc):
    """Callback for MQTT disconnection"""
    logger.warning(f"Disconnected from MQTT broker, return code: {rc}")
    mqtt_connection_status.set(0)


def on_message(client, userdata, msg):
    """Callback for received MQTT messages"""
    mqtt_messages_received.inc()
    
    try:
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        
        logger.debug(f"Received: {topic} = {payload} (retained: {msg.retain})")
        
        # Skip retained messages to avoid processing old data
        if msg.retain:
            logger.debug(f"Skipping retained message: {topic}")
            return
        
        # Parse homie topic structure: homie/device/node/property
        topic_parts = topic.split("/")
        if len(topic_parts) != 4 or topic_parts[0] != "homie":
            logger.debug(f"Ignoring non-homie topic: {topic}")
            return
        
        _, device, node, prop = topic_parts
        
        # Skip homie status messages (starting with $)
        if node.startswith("$") or prop.startswith("$"):
            logger.debug(f"Skipping homie status message: {topic}")
            return
        
        # Process metric
        if prop in METRICS:
            try:
                value = float(payload)
                METRICS[prop].labels(device=device, node=node).set(value)
                mqtt_messages_processed.inc()
                logger.debug(f"Updated metric {prop}(device='{device}', node='{node}') = {value}")
            except ValueError as e:
                logger.warning(f"Invalid numeric value '{payload}' for {topic}: {e}")
                mqtt_messages_errors.inc()
        else:
            logger.debug(f"Unknown property '{prop}' for topic: {topic}")
            # You could add dynamic metric creation here if needed
    
    except Exception as e:
        logger.error(f"Error processing message {msg.topic}: {e}")
        mqtt_messages_errors.inc()


def create_mqtt_client() -> mqtt.Client:
    """Create and configure MQTT client"""
    client = mqtt.Client(client_id=f"{MQTT_CLIENT_ID}_{int(time.time())}")
    
    # Set authentication
    if MQTT_CLIENT_ID and MQTT_CLIENT_SECRET:
        client.username_pw_set(MQTT_CLIENT_ID, MQTT_CLIENT_SECRET)
    
    # Set callbacks
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    
    return client


def main():
    """Main application loop"""
    global running, client
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Starting MQTT to Prometheus Exporter")
    logger.info(f"MQTT Broker: {MQTT_HOST}:{MQTT_PORT}")
    logger.info(f"Prometheus Port: {PROM_EXPORTER_PORT}")
    logger.info(f"MQTT Topic: {MQTT_TOPIC}")
    
    # Start Prometheus HTTP server
    start_http_server(PROM_EXPORTER_PORT)
    
    while running:
        try:
            # Create MQTT client
            client = create_mqtt_client()
            
            logger.info(f"Connecting to MQTT broker {MQTT_HOST}:{MQTT_PORT}")
            client.connect(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
            
            # Start MQTT loop
            client.loop_forever()
            
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            break
        except Exception as e:
            logger.error(f"MQTT connection error: {e}")
            mqtt_connection_status.set(0)
            
            if running:
                logger.info("Reconnecting in 5 seconds...")
                time.sleep(5)
    
    # Cleanup
    if client:
        client.disconnect()
    
    logger.info("Exporter shutdown complete")


if __name__ == "__main__":
    try:
        main()
    except KeyError as e:
        logger.error(f"Missing required environment variable: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
