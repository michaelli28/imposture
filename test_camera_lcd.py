"""Quick test: webcam -> Arduino LCD face display.

Uses OpenCV only (no MediaPipe). Detects if a face is visible and
sends expressions to the Arduino over serial.

Usage: python test_camera_lcd.py
Press 'q' to quit the camera window.
"""

import json
import time

import cv2
import serial

PORT = "/dev/cu.usbmodem1101"
BAUD = 9600

def send(ser, cmd_dict):
    payload = json.dumps(cmd_dict, separators=(",", ":")) + "\n"
    ser.write(payload.encode("utf-8"))
    print(f"-> {payload.strip()}")

def main():
    print(f"Connecting to Arduino on {PORT}...")
    ser = serial.Serial(PORT, BAUD, timeout=1)
    time.sleep(2)  # wait for Arduino reset

    # Drain any startup messages
    while ser.in_waiting:
        print(f"<- {ser.readline().decode(errors='replace').strip()}")

    print("Opening webcam...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open webcam")
        return

    # OpenCV's built-in face detector (no extra models needed)
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    last_emotion = ""
    no_face_count = 0

    send(ser, {"cmd": "display_text", "line1": "Camera Test", "line2": "Starting..."})
    time.sleep(1)
    send(ser, {"cmd": "face", "stage": 2, "emotion": "neutral"})

    print("Running! Press 'q' in the camera window to quit.")
    print("Try: look at camera, look away, move close/far\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)

        if len(faces) > 0:
            no_face_count = 0
            (x, y, w, h) = faces[0]
            frame_h, frame_w = frame.shape[:2]
            face_area = (w * h) / (frame_w * frame_h)

            # Draw rectangle on preview
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Pick emotion based on face position/size
            center_x = x + w // 2
            if face_area > 0.15:
                emotion = "excited"   # very close to camera
            elif center_x < frame_w * 0.3:
                emotion = "concerned" # looking off to the side
            elif center_x > frame_w * 0.7:
                emotion = "concerned"
            else:
                emotion = "happy"     # centered, good

            cv2.putText(frame, f"Face: {emotion}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        else:
            no_face_count += 1
            if no_face_count > 10:
                emotion = "sleeping"  # nobody there
            elif no_face_count > 3:
                emotion = "sad"       # just lost you
            else:
                emotion = last_emotion or "neutral"

            cv2.putText(frame, "No face", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # Only send when emotion changes
        if emotion != last_emotion:
            send(ser, {"cmd": "face", "stage": 2, "emotion": emotion})
            last_emotion = emotion

        # Read any Arduino responses
        while ser.in_waiting:
            line = ser.readline().decode(errors="replace").strip()
            if line:
                print(f"<- {line}")

        cv2.imshow("Wamm Camera Test", frame)
        if cv2.waitKey(100) & 0xFF == ord("q"):
            break

    # Cleanup
    send(ser, {"cmd": "face", "stage": 2, "emotion": "sleeping"})
    cap.release()
    cv2.destroyAllWindows()
    ser.close()
    print("Done!")

if __name__ == "__main__":
    main()
