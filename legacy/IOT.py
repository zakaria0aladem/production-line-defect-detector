import os
import sys

# legacy script: settings are loaded from the main folder (settings.yaml)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from settings import load_settings

settings = load_settings()
TOPICS = settings["mqtt"]["topics"]
ROBOT_READY_VALUE = settings["mqtt"]["robot_ready_value"]

from paho.mqtt import client as mqtt
from paho.mqtt.client import CallbackAPIVersion

clientid = "Defect Detector"
port = settings["mqtt"]["port"]
broker = settings["mqtt"]["broker"]
top=None
bolt=None
bottom=None

def start_mqtt(broker=broker, port=port):
    global top, bolt, bottom
    def on_connect(client, userdata, flags, reason_code, properties=None):
        print("Connected with result code:", reason_code)
        # Subscribe to a test topic once connected
        client.subscribe(TOPICS["top"])
        client.subscribe(TOPICS["bottom"])
        client.subscribe(TOPICS["bolt"])
        client.subscribe(TOPICS["robot_sequence"])

    def on_subscribe(client, userdata, mid, granted_qos, properties=None):
        print(f"Subscription successful! Message ID: {mid}, QoS: {granted_qos}")

    def on_message(client, userdata, msg):
        global top,bolt ,bottom, currentProduct
        print(f"Message received on {msg.topic}: {msg.payload.decode()}")
        topic=msg.topic
        payload = int(msg.payload.decode())  # Convert bytes to string
        if topic==TOPICS["top"] and payload==1:
            top="W"
            print(top)

        elif topic==TOPICS["top"] and payload==2:
            top="B"
            print(top)

        if topic==TOPICS["bolt"] and payload==1:
            bolt="S"
            print(bolt)
        elif topic==TOPICS["bolt"] and payload==2:
            bolt="R"
            print(bolt)
        elif topic==TOPICS["bolt"] and payload==0:
            bolt="null"
            print(bolt)

        if topic==TOPICS["bottom"] and payload==1:
            bottom="W"
            print(bottom)
        elif topic==TOPICS["bottom"] and payload==2:
            bottom="B"
            print(bottom)

        if top is not None and bolt is not None and bottom is not None:
            currentProduct=top + bolt + bottom
            print("Current product:", currentProduct)

        print(f"Message received on {topic}: {payload}")




    client = mqtt.Client(
        client_id=clientid,
        protocol=mqtt.MQTTv311,
        transport="tcp",
        callback_api_version=CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.on_subscribe =on_subscribe
    client.on_message = on_message

    client.connect(broker, port)
    client.loop_forever()
    return lambda: (top, bolt, bottom)


if __name__ == "__main__":
    start_mqtt()


