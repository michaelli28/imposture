"""Test the real CV pipeline with MediaPipe -> Arduino LCD.

Runs posture detection and phone detection, sends results to the LCD.

Usage: python3 test_real_cv.py
Press 'q' to quit the camera window.
"""

import json
import time
import os
import sys

import cv2
import numpy as np
import serial

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from src.cv_pipeline import (
    compute_posture_score,
    posture_label,
    extract_features,
    CALIB_FRAMES,
)

PORT = "/dev/cu.usbmodem1101"
BAUD = 9600

# Thresholds
SCORE_BAD = 70.0
SCORE_GOOD = 85.0

def send(ser, cmd_dict):
    payload = json.dumps(cmd_dict, separators=(",", ":")) + "\n"
    ser.write(payload.encode("utf-8"))
    print(f"-> {payload.strip()}")


def main():
    print(f"Connecting to Arduino on {PORT}...")
    ser = serial.Serial(PORT, BAUD, timeout=1)
    time.sleep(2)

    while ser.in_waiting:
        print(f"<- {ser.readline().decode(errors='replace').strip()}")

    print("Opening webcam...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open webcam")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Init MediaPipe
    print("Loading MediaPipe models...")
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe import Image, ImageFormat

    pose_model = os.path.join(os.path.dirname(__file__), "pose_landmarker.task")
    det_model = os.path.join(os.path.dirname(__file__), "object_detector.tflite")

    landmarker = None
    detector = None

    if os.path.exists(pose_model):
        pose_options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=pose_model,
                delegate=mp_python.BaseOptions.Delegate.CPU,
            ),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        landmarker = mp_vision.PoseLandmarker.create_from_options(pose_options)
        print("PoseLandmarker loaded")
    else:
        print(f"WARNING: {pose_model} not found")

    if os.path.exists(det_model):
        det_options = mp_vision.ObjectDetectorOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=det_model,
                delegate=mp_python.BaseOptions.Delegate.CPU,
            ),
            running_mode=mp_vision.RunningMode.VIDEO,
            score_threshold=0.4,
            max_results=10,
        )
        detector = mp_vision.ObjectDetector.create_from_options(det_options)
        print("ObjectDetector loaded")
    else:
        print(f"WARNING: {det_model} not found")

    # Calibration phase
    send(ser, {"cmd": "display_text", "line1": "Sit up straight", "line2": "Calibrating..."})
    print("\n=== CALIBRATION ===")
    print(f"Sit in your best posture for {CALIB_FRAMES} frames...")

    reference = None
    calib_features = []
    frame_ts = 0
    frame_count = 0

    while frame_count < CALIB_FRAMES:
        ret, frame = cap.read()
        if not ret:
            continue

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_ts += 33  # ~30fps timestamps
        mp_img = Image(image_format=ImageFormat.SRGB, data=rgb)

        if landmarker:
            result = landmarker.detect_for_video(mp_img, frame_ts)
            if result.pose_landmarks and len(result.pose_landmarks) > 0:
                lm = result.pose_landmarks[0]
                features = extract_features(lm, w, h)
                calib_features.append(features)
                frame_count += 1

                # Show progress
                progress = frame_count * 16 // CALIB_FRAMES
                bar = "#" * progress + "-" * (16 - progress)
                cv2.putText(frame, f"Calibrating: {frame_count}/{CALIB_FRAMES}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            else:
                cv2.putText(frame, "No pose detected - sit in view", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.imshow("Wamm CV Test", frame)
        if cv2.waitKey(33) & 0xFF == ord("q"):
            cap.release()
            cv2.destroyAllWindows()
            ser.close()
            return

    # Average calibration features
    if calib_features:
        reference = {}
        for key in calib_features[0]:
            reference[key] = sum(f[key] for f in calib_features) / len(calib_features)
        print(f"Calibration complete! Reference: {reference}")
        send(ser, {"cmd": "display_text", "line1": "Calibrated!", "line2": "Starting..."})
        time.sleep(1)
    else:
        print("WARNING: Calibration failed, using absolute scoring only")

    # Main loop
    send(ser, {"cmd": "face", "stage": 2, "emotion": "happy"})
    last_emotion = "happy"
    score_buffer = []
    phone_frames = 0
    no_phone_frames = 0
    phone_active = False

    print("\n=== RUNNING ===")
    print("Monitoring posture and phone usage. Press 'q' to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_ts += 33
        mp_img = Image(image_format=ImageFormat.SRGB, data=rgb)

        score = None
        label = ""
        emotion = last_emotion

        # Posture detection
        if landmarker:
            try:
                result = landmarker.detect_for_video(mp_img, frame_ts)
                if result.pose_landmarks and len(result.pose_landmarks) > 0:
                    lm = result.pose_landmarks[0]
                    score, metrics = compute_posture_score(lm, w, h, reference)

                    score_buffer.append(score)
                    if len(score_buffer) > 15:
                        score_buffer.pop(0)
                    smoothed = round(sum(score_buffer) / len(score_buffer), 1)

                    label = posture_label(smoothed)

                    if smoothed >= SCORE_GOOD:
                        emotion = "happy"
                    elif smoothed >= SCORE_BAD:
                        emotion = "neutral"
                    elif smoothed >= 50:
                        emotion = "concerned"
                    else:
                        emotion = "sad"

                    # Draw on preview
                    color = (0, 255, 0) if smoothed >= SCORE_BAD else (0, 0, 255)
                    cv2.putText(frame, f"Posture: {smoothed} ({label})", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                    cv2.putText(frame, f"Spine: {metrics['spine_angle_deg']}  Neck: {metrics['neck_angle_deg']}", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                else:
                    cv2.putText(frame, "No pose detected", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    emotion = "sleeping"
            except Exception as e:
                cv2.putText(frame, f"Pose error: {e}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        # Phone detection
        if detector:
            try:
                det_result = detector.detect_for_video(mp_img, frame_ts)
                phone_detected = any(
                    "cell phone" in cat.category_name.lower()
                    for detection in det_result.detections
                    for cat in detection.categories
                )
                if phone_detected:
                    phone_frames += 1
                    no_phone_frames = 0
                    if phone_frames > 15:  # ~0.5s sustained
                        phone_active = True
                        emotion = "angry"
                        cv2.putText(frame, "PHONE DETECTED!", (10, 90),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                else:
                    no_phone_frames += 1
                    if no_phone_frames > 10:
                        phone_frames = 0
                        phone_active = False
            except Exception:
                pass

        # Update LCD when emotion changes
        if emotion != last_emotion:
            send(ser, {"cmd": "face", "stage": 2, "emotion": emotion})
            last_emotion = emotion

        # Show score on LCD periodically (every ~3s)
        if score is not None and not phone_active:
            if int(frame_ts / 33) % 90 == 0:
                send(ser, {"cmd": "display_text", "line1": f"Score: {smoothed}", "line2": label})
                time.sleep(0.05)
                send(ser, {"cmd": "face", "stage": 2, "emotion": emotion})

        # Read Arduino responses
        while ser.in_waiting:
            line = ser.readline().decode(errors="replace").strip()
            if line:
                print(f"<- {line}")

        cv2.imshow("Wamm CV Test", frame)
        if cv2.waitKey(33) & 0xFF == ord("q"):
            break

    send(ser, {"cmd": "face", "stage": 2, "emotion": "sleeping"})
    if landmarker:
        landmarker.close()
    if detector:
        detector.close()
    cap.release()
    cv2.destroyAllWindows()
    ser.close()
    print("Done!")


if __name__ == "__main__":
    main()
