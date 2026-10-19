import os
import sys

# legacy script: settings are loaded from the main folder (settings.yaml)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from settings import load_settings

settings = load_settings()
TOPICS = settings["mqtt"]["topics"]
ROBOT_READY_VALUE = settings["mqtt"]["robot_ready_value"]

from ultralytics import YOLO
import cv2
from paho.mqtt import client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import time

last_action_time = 0
action_delay = 5

clientid = "Defect Detector"
port = settings["mqtt"]["port"]
broker = settings["mqtt"]["broker"]
top=None
bolt=None
bottom=None
currentProduct=None
robotState=None

def on_connect(client, userdata, flags, reason_code, properties=None):
    print("Connected with result code:", reason_code)
    # Subscribe to topics
    client.subscribe(TOPICS["top"])
    client.subscribe(TOPICS["bottom"])
    client.subscribe(TOPICS["bolt"])
    client.subscribe(TOPICS["robot_sequence"])

def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    print(f"Subscription successful! Message ID: {mid}, QoS: {granted_qos}")

def on_message(client, userdata, msg):
    global top, bolt, bottom, currentProduct, robotState
    print(f"📩 Message received on {msg.topic}: {msg.payload.decode()}")
    topic = msg.topic
    payload = int(msg.payload.decode())

    if topic == TOPICS["top"]:
        if payload == 1:
            top = "W"
        elif payload == 2:
            top = "B"
        print(f"🔹 Top updated: {top}")

    if topic == TOPICS["bolt"]:
        if payload == 1:
            bolt = "S"
        elif payload == 2:
            bolt = "R"
        elif payload == 0:
            bolt = "null"
        print(f"🔹 Bolt updated: {bolt}")

    if topic == TOPICS["bottom"]:
        if payload == 1:
            bottom = "W"
        elif payload == 2:
            bottom = "B"
        print(f"🔹 Bottom updated: {bottom}")

    if top is not None and bolt is not None and bottom is not None:
        currentProduct = top + bolt + bottom
        print(f"✅ Current product set: {currentProduct}")

    if topic == TOPICS["robot_sequence"]:
        print("📩 Robot state message received:", payload)  # debug message
        if payload == ROBOT_READY_VALUE:
            robotState = "ready"
            print("🤖 Robot state set to READY")

def publish_message(client, topic, message):
    result = client.publish(topic, message)
    status = result[0]
    if status == 0:
        print(f"📤 Sent '{message}' to topic '{topic}'")
    else:
        print(f"❌ Failed to send message to topic {topic}")

def start_mqtt(broker=broker, port=port):
    client = mqtt.Client(
        client_id=clientid,
        protocol=mqtt.MQTTv311,
        transport="tcp",
        callback_api_version=CallbackAPIVersion.VERSION2
    )
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    client.connect(broker, port)
    client.loop_start()
    return client

def main():
    global currentProduct, robotState,last_action_time, action_delay
    model = YOLO(settings["model"])
    client = start_mqtt()

    cap = cv2.VideoCapture(0)
    out = None  # Initialize output class

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        results = model.predict(frame, conf=0.5, device="cuda")
        detectedProduct = []
        annotated_frame = results[0].plot()

        if len(results[0].boxes.cls) > 0:
            for c in results[0].boxes.cls:
                detectedProduct.append(int(c))
        else:
            print("⚠️ No products detected!")

        # Debugging info
        print(f"🔍 DetectedProduct: {detectedProduct}, CurrentProduct: {currentProduct}, RobotState: {robotState}")

        if detectedProduct:
            if detectedProduct[0] == 0 and currentProduct == "WSB":
                out = detectedProduct[0]
                print("✅ Match: WSB")
            elif detectedProduct[0] == 1 and currentProduct == "BRW":
                out = detectedProduct[0]
                print("✅ Match: BRW")
            elif detectedProduct[0] == 2 and currentProduct == "WRB":
                out = detectedProduct[0]
                print("✅ Match: WRB")
            elif detectedProduct[0] == 3 and currentProduct == "BSW":
                out = detectedProduct[0]
                print("✅ Match: BSW")
            elif detectedProduct[0] == 4 and currentProduct == "WRW":
                out = detectedProduct[0]
                print("✅ Match: WRW")
            elif detectedProduct[0] == 5 and currentProduct == "WSW":
                out = detectedProduct[0]
                print("✅ Match: WSW")
            elif detectedProduct[0] == 6 and currentProduct == "BRB":
                out = detectedProduct[0]
                print("✅ Match: BRB")
            elif detectedProduct[0] == 7 and currentProduct == "BSB":
                out = detectedProduct[0]
                print("✅ Match: BSB")
            elif detectedProduct[0] == 8 and currentProduct is not None and "null" in currentProduct:
                print("⚠️ Null detected")
            elif detectedProduct[0] == 8:
                out = detectedProduct[0]
                print("❌ Defective: no cylinder")
            elif detectedProduct[0] == 9:
                out = detectedProduct[0]
                print("❌ Defective: no top")
            else:
                print("❓ Unknown object")

        # Debugging robot decision
        # inside your while loop
        if robotState == "ready":
            current_time = time.time()
            if current_time - last_action_time >= action_delay:
                print("🤖 Robot is READY")
                if detectedProduct:  # make sure list is not empty
                    first_detected = detectedProduct[0]

                    if out is not None and out == first_detected:
                        print("📦 Product verified, sending ACC command")
                        publish_message(client, TOPICS["command"], "ACC")

                    elif out is not None and out != first_detected:
                        print("⚠️ Robot ready but product defect or not detected")
                        publish_message(client, TOPICS["command"], "REJ")

                last_action_time = current_time  # reset delay timer

        cv2.imshow("YOLOv8 Live Feed", annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
