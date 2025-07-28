#!/usr/bin/python3
"""
program to read datalogger data from MQTT topic
and writing this data to local Files
"""
import os
import json
import time
import datetime
import argparse
import logging
import threading
# non std modules
import yaml
import paho.mqtt.client as mqtt
import paho.mqtt.subscribe as subscribe


logging.basicConfig(level=logging.INFO)

# global: table definition
definition = None
# global
stats = {
    "received": 0,
    "skipped": 0,
    "written": 0,
}

data = {}

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    """
    called on connect

    :param client: reference to MQTT client
    :param userdata: dont know
    :param flag: dont know
    :param rc: dont know
    """
    logger.info("Connected with result code " + str(rc))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    topic = "/".join(("homie", "#"))
    logger.info("subscribing to topic %s", topic)
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
        stats["received"] += 1
        logger.debug("%s : %s : %s", msg.topic, msg.retain, msg.payload.decode("utf-8"))
        # on first there are some retained messages
        if not msg.retain:
            _, device, node, prop = msg.topic.split("/")
            value = float(msg.payload.decode("utf-8"))
            ts = time.time()
            datestring = datetime.date.fromtimestamp(ts).isoformat() # datestring from timestamp
            filename = os.path.join(args.outdir, args.project, f"{args.tablename}_{datestring}.csv")
            csv_line = f"{int(time.time())};{device};{node};{prop};{value}"
            logger.debug(filename + " : " + csv_line)
            # on file creating, write header
            if not os.path.isfile(filename):
                open(filename, "wt").write("\t".join(headers) + "\n")
            open(filename, "at").write(csv_line + "\n")
            stats["written"] += 1
        else:
            stats["skipped"] += 1
    except Exception as exc:
        stats["skipped"] += 1
        logger.exception(exc)
        pass

def read_config():
    """
    reading table definition file, should be called periodically
    re-definig global variable definition
    """
    filename = os.path.join(args.configdir, args.project, f"{args.tablename}.yml")
    global definition
    new_definition = yaml.safe_load(open(filename).read())
    if definition and definition == new_definition:
        logging.debug("definition did not change in definition file")
    else:
        definition = new_definition
        logger.info("showing table definition")
        logger.info(yaml.dump(definition, indent=2))
    logger.debug("showing some statistics")
    logger.info(stats)
    logger.debug(f"re-reading config file very {args.refresh}")
    threading.Timer(args.refresh, read_config).start()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='write published MQTT data to local datalogger files')
    parser.add_argument('-H', dest='mqtt_host', default=os.environ["MQTT_HOST"] if os.environ.get("MQTT_HOST") else "127.0.0.1", help='MQTT Server to use')
    parser.add_argument('-P', dest='mqtt_port', type=int, default=int(os.environ["MQTT_PORT"]) if os.environ.get("MQTT_PORT") else 1833, help='TCP Port the MQTT Server is listening on')
    parser.add_argument('--client-id', dest='client_id', default=os.environ["MQTT_CLIENT_ID"] if os.environ.get("MQTT_CLIENT_ID") else "mqtt-service-notification", help='MQTT uername to use')
    parser.add_argument('--client-secret', dest='client_secret', default=os.environ["MQTT_CLIENT_SECRET"] if os.environ.get("MQTT_CLIENT_SECRET") else None, help='MQTT password to use')
    parser.add_argument('-T', dest='mqtt_topic', default=os.environ["MQTT_TOPIC"] if os.environ.get("MQTT_TOPIC") else "datalogger", help='MQTT base topic to use, will be expanded by project and tablename')
    parser.add_argument('-c', dest='configdir', default=os.environ["DATALOGGER_CONFIG_DIR"] if os.environ.get("DATALOGGER_CONFIG_DIR") else "/usr/src/app/config", help='datalogger base directory, to find table configuration in meta subdirectory')
    parser.add_argument('-o', dest='outdir', default=os.environ["DATALOGGER_HOT_DIR"] if os.environ.get("DATALOGGER_HOT_DIR") else "/usr/src/app/hot", help='datalogger base directory, to find table configuration in meta subdirectory')
    parser.add_argument('-i', dest='homie_id', default=os.environ["HOMIE_ID"] if os.environ.get("HOMIE_ID") else None, help='homie id to listen for')
    parser.add_argument('-p', dest='project', default=os.environ["DATALOGGER_PROJECT"] if os.environ.get("DATALOGGER_PROJECT") else None, help='datalogger project')
    parser.add_argument('-t', dest='tablename', default=os.environ["DATALOGGER_TABLENAME"] if os.environ.get("DATALOGGER_TABLENAME") else None, help='datalogger tablename')
    parser.add_argument('-r', dest='refresh', type=int, default=int(os.environ["REFRESH"]) if os.environ.get("REFRESH") else 60, help='how often to refresh config')
    args = parser.parse_args()
    logger = logging.getLogger(__name__)
    logger.info("showing enviroment variables")
    logger.info(yaml.dump(dict(os.environ), indent=2))
    # some consts
    if args.client_id and args.client_secret:
        auth = {
            "username": args.client_id,
            "password": args.client_secret
        }
    # read config initially and start Thread to re-read peridically
    read_config()
    # get ts keyname
    ts_keyname = [key for key in definition["description"] if definition["description"][key]["coltype"] == "ts"][0] # one and only
    delimiter = definition["delimiter"] # shortcut
    # create list of headers, according to position in csv file
    headers = [key for key in sorted(definition["description"], key=lambda a: definition["description"][a]["colpos"])]
    # first get device config

    def get_payload(topic):
        """
        shorty to get one single persistent value
        """
        logger.info("getting %s", topic)
        msg = subscribe.simple(topic, hostname=args.mqtt_host)
        return msg.payload.decode("utf-8")

    # TODO: is it necessary to know the home configuration??
    conf_topic = "/".join(("homie", args.homie_id))
    keys = ['$homie', '$name', '$state', '$implementation', '$nodes']
    for key in keys:
        msg = subscribe.simple(f"{conf_topic}/{key}", hostname=args.mqtt_host)
        data[key] = msg.payload.decode("utf-8")
    data["nodes"] = {}
    # next get node config
    for node in data["$nodes"].split(","):
        node_topic = f"{conf_topic}/{node}"
        data["nodes"][node] = {
            "_node_topic": node_topic,
            "$name": subscribe.simple(f"{node_topic}/$name", hostname=args.mqtt_host).payload.decode("utf-8"),
            "$type": subscribe.simple(f"{node_topic}/$type", hostname=args.mqtt_host).payload.decode("utf-8"),
            "$properties": subscribe.simple(f"{node_topic}/$properties", hostname=args.mqtt_host).payload.decode("utf-8"),
        }
        # get properties
        for properti in data["nodes"][node]["$properties"].split(","):
            data["nodes"][node][properti] = {
                "$name": None,
                "$datatype": None,
                "$format": None,
                "$unit": None,
            }
            # get property informations
            for key in data["nodes"][node][properti]:
                property_topic = f"{node_topic}/{properti}/{key}"
                data["nodes"][node][properti][key] = get_payload(property_topic)
    print(json.dumps(data, indent=4))
    while True:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(args.mqtt_host, args.mqtt_port, 60)
        # Blocking call that processes network traffic, dispatches callbacks and
        # handles reconnecting.
        # Other loop*() functions are available that give a threaded interface and a
        # manual interface.
        client.loop_forever()
        logger.error("forever loop ended, trying reconnect in 5 s")
        time.sleep(5)

