from ultralytics import YOLO
import cv2
from paho.mqtt import client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import time
import argparse

from settings import load_settings

#  Config (all values come from settings.yaml, see settings.example.yaml)
parser = argparse.ArgumentParser(description="YOLOv8 defect detector for the production line")
parser.add_argument("--settings", default=None, help="path to settings file (default: settings.yaml)")
parser.add_argument("--camera", type=int, default=None, help="camera index (overrides settings)")
parser.add_argument("--device", default=None, help="cuda or cpu (overrides settings)")
args = parser.parse_args()

settings = load_settings(args.settings)

clientid = settings["mqtt"]["client_id"]
broker = settings["mqtt"]["broker"]
port = settings["mqtt"]["port"]
TOPICS = settings["mqtt"]["topics"]
ROBOT_READY_VALUE = settings["mqtt"]["robot_ready_value"]
CAM = args.camera if args.camera is not None else settings["camera"]  # camera index
device = args.device or settings["device"]  # GPU if you want to change to cpu, write: cpu
MODEL_PATH = settings["model"]
CONF = settings["conf"]

# timing
action_delay = settings["timing"]["action_delay"]  # minimum time between commands to avoid spamming
check_delay = settings["timing"]["check_delay"]   # wait this many seconds after robot ready for product to settle
display_duration = settings["timing"]["display_duration"]  # how long to display ACC/REJ banner (seconds)

# Globals (shared with MQTT callbacks)
top = None
bolt = None
bottom = None
currentProduct = None
robotState = None

# runtime state
check_start_time = None
last_action_time = 0
last_command = None  # "ACC" or "REJ"
last_command_time = 0
last_command_detail = ""  # extra text to display with ACC/REJ
out = None  # last detected code considered "match"

# Map detected integer code -> product label
code_to_label = {
    0: "WSB",
    1: "BRW",
    2: "WRB",
    3: "BSW",
    4: "WRW",
    5: "WSW",
    6: "BRB",
    7: "BSB",
    8: "DEFECT_NO_CYL",
    9: "DEFECT_NO_TOP"
}


# MQTT callbacks
def on_connect(client, userdata, flags, reason_code, properties=None):
    print("Connected with result code:", reason_code)

    client.subscribe(TOPICS["top"])
    client.subscribe(TOPICS["bottom"])
    client.subscribe(TOPICS["bolt"])
    client.subscribe(TOPICS["robot_sequence"])


def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    print(f"Subscription successful! Message ID: {mid}, QoS: {granted_qos}")


def on_message(client, userdata, msg):
    global top, bolt, bottom, currentProduct, robotState

    try:
        payload = int(msg.payload.decode())
    except Exception:
        print("Received non-int payload:", msg.payload)
        return

    topic = msg.topic
    print(f"📩 {topic} -> {payload}")

    if topic == TOPICS["top"]:
        if payload == 1:
            top = "W"
        elif payload == 2:
            top = "B"
        else:
            top = None

    elif topic == TOPICS["bolt"]:
        if payload == 1:
            bolt = "S"
        elif payload == 2:
            bolt = "R"
        elif payload == 0:
            bolt = "null"
        else:
            bolt = None

    elif topic == TOPICS["bottom"]:
        if payload == 1:
            bottom = "W"
        elif payload == 2:
            bottom = "B"
        else:
            bottom = None

    if top and bolt and bottom:
        currentProduct = top + bolt + bottom
        print(f"✅ CurrentProduct set: {currentProduct}")

    if topic == TOPICS["robot_sequence"]:
        if payload == ROBOT_READY_VALUE:
            robotState = "ready"
            print("🤖 Robot set to READY")


#  Publisher wrapper
def publish_message(client, topic, message, detail=""):
    global last_command, last_command_time, last_command_detail, CAM, device

    result = client.publish(topic, message)
    status = result[0]

    if status == 0:
        last_command = message
        last_command_time = time.time()
        last_command_detail = detail
        print(f"📤 Sent '{message}' to {topic} ({detail})")
    else:
        print(f"❌ Failed to send '{message}' to {topic}")


def start_mqtt():
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


# Drawing helpers
def draw_label_background(frame, text, pos, bg_color=(0, 0, 0), text_color=(255, 255, 255),
                          font_scale=0.7, thickness=2):
    font = cv2.FONT_HERSHEY_SIMPLEX
    (w, h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    x, y = pos

    tl = (x, y - h - baseline - 8)
    br = (x + w + 16, y + 4)

    cv2.rectangle(frame, tl, br, bg_color, -1)
    cv2.putText(frame, text, (x + 8, y - baseline - 2), font,
                font_scale, text_color, thickness, cv2.LINE_AA)


def draw_center_banner(frame, text, color=(0, 200, 0), text_color=(255, 255, 255),
                       font_scale=1.0, thickness=2):
    font = cv2.FONT_HERSHEY_SIMPLEX
    h_frame, w_frame = frame.shape[:2]

    (w, h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    x = (w_frame - w) // 2
    y = h_frame - 40

    tl = (x - 20, y - h - baseline - 10)
    br = (x + w + 20, y + 10)

    cv2.rectangle(frame, tl, br, color, -1)
    cv2.putText(frame, text, (x, y - baseline), font,
                font_scale, text_color, thickness, cv2.LINE_AA)



def main():
    global out, check_start_time, last_action_time, robotState, currentProduct, CAM, device

    model = YOLO(MODEL_PATH)
    client = start_mqtt()

    cap = cv2.VideoCapture(CAM)

    # Fullscreen window
    cv2.namedWindow("Classification", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Classification", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    if not cap.isOpened():
        print("Camera not opened")
        return

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Run detection
        results = model.predict(frame, conf=CONF, device=device)
        annotated_frame = results[0].plot()

        detectedProduct = []
        if len(results[0].boxes.cls) > 0:
            for c in results[0].boxes.cls:
                detectedProduct.append(int(c))

        detected_code = detectedProduct[0] if detectedProduct else None
        detected_label = code_to_label.get(detected_code, "None") if detected_code is not None else "None"

        # Robot action logic
        if robotState == "ready":
            now = time.time()

            if check_start_time is None:
                check_start_time = now
                print("⏳ Robot ready — starting settle timer...")

            elif now - check_start_time >= check_delay and now - last_action_time >= action_delay:
                print("🔎 Checking product after settle delay...")

                if detected_code is not None and currentProduct is not None:
                    label = code_to_label.get(detected_code, "Unknown")

                    # ✅ Normal match
                    if label == currentProduct:
                        publish_message(client, TOPICS["command"], "ACC", detail=f"{label}")

                    # ✅ Special case: expected null bolt & detected no cylinder → treat as ACC
                    elif "null" in currentProduct and label == "DEFECT_NO_CYL":
                        publish_message(client, TOPICS["command"], "ACC",
                                        detail=f"{currentProduct} (null bolt accepted)")

                    else:
                        publish_message(client, TOPICS["command"], "REJ",
                                        detail=f"{label} != {currentProduct}")
                else:
                    publish_message(client, TOPICS["command"], "REJ", detail="No detection")

                last_action_time = now
                check_start_time = None
                robotState = None

        # Overlay drawing
        f = annotated_frame

        draw_label_background(f, f"Robot: {robotState or 'idle'}", (10, 30))
        draw_label_background(f, f"Expected: {currentProduct or 'None'}", (10, 65))
        draw_label_background(f, f"Detected: {detected_label}", (10, 100))

        if last_command and (time.time() - last_command_time) <= display_duration:
            banner_text = f"{last_command}  {last_command_detail}"

            if last_command == "ACC":
                draw_center_banner(f, banner_text, color=(0, 150, 0))
            else:
                draw_center_banner(f, banner_text, color=(0, 0, 180))

        # show in fullscreen window
        cv2.imshow("Classification", f)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
