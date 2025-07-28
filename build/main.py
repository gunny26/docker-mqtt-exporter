#!/usr/bin/python3
"""
program to read data from Mosquitto Server and export to prometheus
"""
import json
import logging
import os
import time
# non std modules
import paho.mqtt.client as mqtt
# import paho.mqtt.subscribe as subscribe
from prometheus_client import start_http_server, Gauge, Counter


logging.basicConfig(level=logging.INFO)
logging.info("showing enviroment variables")
logging.info(json.dumps(dict(os.environ), indent=2))


MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1833"))
MQTT_CLIENT_ID = os.environ["MQTT_CLIENT_ID"]  # mandatory
MQTT_CLIENT_SECRET = os.environ["MQTT_CLIENT_SECRET"]  # mandatory
DEBUG_LEVEL = os.environ.get("DEBUG_LEVEL", "INFO")
PROM_EXPORTER_PORT = 9100  # fixed to make HEALTHCHECK working

class MyCounter(Counter):
    """ counter class with set method """

    def set(self, value: float) -> None:
        """Set gauge to the given value."""
        self._raise_if_not_observable()
        self._value.set(float(value))

metrics = {
    "homie_property_temperature": Gauge('homie_property_temperature', 'Temperature in degree celcius', ["device", "node"]),
    "homie_property_humidity": Gauge('homie_property_humidity', 'Humidity in percent', ["device", "node"]),
    "homie_property_light": Gauge("homie_property_light", "Light strength in lumen", ["device", "node"]),
    "homie_property_energy5": Gauge("homie_property_energy5", "Energy consumption last five 5min", ["device", "node"]),
    "homie_property_energyhour": Gauge("homie_property_energyhour", "Energy consumption last hour", ["device", "node"]),
    "homie_property_totalenergy": Gauge("homie_property_totalenergy", "Energy consumption total", ["device", "node"]),
    "homie_property_energy": MyCounter("homie_property_energy", "S0 impulses", ["device", "node"]),
}


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    """
    called on connect

    :param client: reference to MQTT client
    :param userdata: dont know
    :param flag: dont know
    :param rc: dont know
    """
    logging.info("Connected with result code {rc}")
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    topic = "/".join(("homie", "#"))
    logging.info(f"subscribing to topic {topic}")
    client.subscribe(topic)


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    """
    called on every message

    :param client: reference to MQTT Client
    :param userdata: dont know
    :param msg: topic and payload information
    """
    try:
        logging.debug(f"{msg.topic} : {msg.retain} : {msg.payload.decode('utf-8')}")
        # on first there are some retained messages
        if not msg.retain:
            logging.debug(msg.topic)
            _, device, node, prop = msg.topic.split("/")
            value = msg.payload.decode("utf-8")
            if node[0] != "$":  # some status data from homie
                # {"timestamp": 1629144200, "device": "e166bf00", "node": "ky018", "property": "light", "value": -0.00976563}
                metric_name = f'homie_property_{prop}'
                if metrics.get(metric_name):
                    logging.info(f"exporting {metric_name} = {value}")
                    metrics[metric_name].labels(device, node).set(float(value))
                else:
                    logging.info("UNDEFINED METRIC : {metric_name}")
                    logging.info(f"homie_property_{prop}(device='{device}', node='{node}') {float(value)}")
        else:
            logging.debug(f"skipping {msg.topic}")
    except Exception as exc:
        logging.exception(exc)


def main():
    # some consts
    if MQTT_CLIENT_ID and MQTT_CLIENT_SECRET:
        auth = {
            "username": MQTT_CLIENT_ID,
            "password": MQTT_CLIENT_SECRET
        }
    start_http_server(PROM_EXPORTER_PORT)
    while True:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        # Blocking call that processes network traffic, dispatches callbacks and
        # handles reconnecting.
        # Other loop*() functions are available that give a threaded interface and a
        # manual interface.
        client.loop_forever()
        logging.error("forever loop ended, trying reconnect in 5 s")
        time.sleep(5)


if __name__ == "__main__":
    if DEBUG_LEVEL == "DEBUG":
        logging.getLogger().setLevel(logging.DEBUG)
    elif DEBUG_LEVEL == "INFO":
        logging.getLogger().setLevel(logging.INFO)
    elif DEBUG_LEVEL == "ERROR":
        logging.getLogger().setLevel(logging.ERROR)
    main()
