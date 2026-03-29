"""
posture_analyzer.py
-------------------
Webcam/laptop-camera posture grader using modern MediaPipe (0.10.13+).

Camera note: input is rotated 90° CCW from the webcam, so every frame is
corrected with cv2.ROTATE_90_CLOCKWISE before any processing or display.

Features:
  - Calibration: press SPACE at startup to capture a reference "good posture",
    or S to skip and use absolute geometry scoring only.
  - Press R mid-session to recalibrate.
  - Posture scoring: 0–100, blending personal reference (80%) + absolute
    geometry (20%). Printed to console every second.
  - Posture strike tracker: warning after 30s of sub-Good posture,
    strike after 60s. Timer resets when posture recovers.
  - Phone tracker: alert if phone visible >= 5s in any 10s window,
    with a running violation count.

Setup:
    pip install mediapipe opencv-python numpy

    curl -o pose_landmarker.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task
    curl -o object_detector.tflite https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/latest/efficientdet_lite0.tflite

Usage:
    python posture_analyzer.py
"""

import cv2
import numpy as np
import time
import os

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from mediapipe import Image, ImageFormat

# ── Model paths ───────────────────────────────────────────────────────────────
SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
POSE_MODEL     = os.path.join(SCRIPT_DIR, "pose_landmarker.task")
DETECTOR_MODEL = os.path.join(SCRIPT_DIR, "object_detector.tflite")

# ── Calibration settings ──────────────────────────────────────────────────────
CALIB_FRAMES      = 60    # frames to average for reference pose
CALIB_COUNTDOWN   = 3     # seconds of countdown before capture
REF_WEIGHT        = 0.8   # reference score contribution
ABS_WEIGHT        = 0.2   # absolute geometry score contribution
REF_BAD_THRESHOLD = 20.0  # drift before reference score hits 0

# ── Posture strike settings ───────────────────────────────────────────────────
POSTURE_WARN_SEC   = 30
POSTURE_STRIKE_SEC = 60

# ── Phone tracker settings ────────────────────────────────────────────────────
PHONE_WINDOW_SEC = 10
PHONE_ALERT_SEC  = 5

# ── Landmark indices ──────────────────────────────────────────────────────────
NOSE           = 0
LEFT_EAR       = 7
RIGHT_EAR      = 8
LEFT_SHOULDER  = 11
RIGHT_SHOULDER = 12
LEFT_HIP       = 23
RIGHT_HIP      = 24

POSE_CONNECTIONS = [
    (0, 7), (0, 8),
    (7, 11), (8, 12),
    (11, 12),
    (11, 23), (12, 24),
    (23, 24),
]

# ── Camera helper ─────────────────────────────────────────────────────────────

def read_frame(cap):
    """Read a frame and immediately correct the 90° CCW rotation."""
    ret, frame = cap.read()
    if not ret:
        return False, None
    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    return True, frame

# ── Geometry helpers ──────────────────────────────────────────────────────────

def midpoint(p1, p2):
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)

def lm_xy(landmarks, idx, w, h):
    lm = landmarks[idx]
    return (lm.x * w, lm.y * h)

def vertical_angle(p_top, p_bottom):
    dx = p_bottom[0] - p_top[0]
    dy = p_bottom[1] - p_top[1]
    return float(np.degrees(np.arctan2(abs(dx), abs(dy) + 1e-6)))

def score_from_deviation(deviation, bad_threshold):
    return max(0.0, 100.0 * (1.0 - abs(deviation) / bad_threshold))

# ── Feature extraction ────────────────────────────────────────────────────────

def extract_features(landmarks, w, h):
    """
    Normalised posture features, all divided by shoulder_width for
    scale-invariance regardless of distance from camera.
    """
    l_ear      = lm_xy(landmarks, LEFT_EAR, w, h)
    r_ear      = lm_xy(landmarks, RIGHT_EAR, w, h)
    l_shoulder = lm_xy(landmarks, LEFT_SHOULDER, w, h)
    r_shoulder = lm_xy(landmarks, RIGHT_SHOULDER, w, h)
    l_hip      = lm_xy(landmarks, LEFT_HIP, w, h)
    r_hip      = lm_xy(landmarks, RIGHT_HIP, w, h)

    mid_shoulder   = midpoint(l_shoulder, r_shoulder)
    mid_hip        = midpoint(l_hip, r_hip)
    mid_ear        = midpoint(l_ear, r_ear)
    shoulder_width = max(abs(l_shoulder[0] - r_shoulder[0]), 10)

    return {
        "spine_angle":     vertical_angle(mid_shoulder, mid_hip),
        "ear_forward":     (mid_shoulder[0] - mid_ear[0]) / shoulder_width * 100,
        "neck_angle":      vertical_angle(mid_ear, mid_shoulder),
        "shoulder_diff":   abs(l_shoulder[1] - r_shoulder[1]) / shoulder_width * 100,
        "ear_height_diff": abs(l_ear[1] - r_ear[1]) / shoulder_width * 100,
    }

# ── Scoring ───────────────────────────────────────────────────────────────────

def absolute_score(features):
    # Ear-forward allowance is wider (30) to account for 45° camera angle
    s1 = score_from_deviation(features["spine_angle"],                        bad_threshold=20.0)
    s2 = score_from_deviation(max(0.0, features["ear_forward"] - 30.0),       bad_threshold=40.0)
    s3 = score_from_deviation(features["neck_angle"],                         bad_threshold=40.0)
    s4 = score_from_deviation(max(0.0, features["shoulder_diff"] - 5.0),      bad_threshold=25.0)
    s5 = score_from_deviation(max(0.0, features["ear_height_diff"] - 5.0),    bad_threshold=25.0)
    weights = [0.30, 0.30, 0.20, 0.10, 0.10]
    return sum(w * s for w, s in zip(weights, [s1, s2, s3, s4, s5]))

def reference_score(features, reference):
    scores = []
    for key in features:
        dev = features[key] - reference[key]
        scores.append(score_from_deviation(dev, bad_threshold=REF_BAD_THRESHOLD))
    return sum(scores) / len(scores)

def analyze_posture(landmarks, w, h, reference=None):
    features = extract_features(landmarks, w, h)
    abs_s    = absolute_score(features)
    if reference is not None:
        ref_s = reference_score(features, reference)
        total = ABS_WEIGHT * abs_s + REF_WEIGHT * ref_s
    else:
        total = abs_s
    metrics = {
        "spine_angle_deg":    round(features["spine_angle"], 1),
        "ear_forward_norm":   round(features["ear_forward"], 1),
        "neck_angle_deg":     round(features["neck_angle"], 1),
        "shoulder_diff_norm": round(features["shoulder_diff"], 1),
    }
    return round(total, 1), metrics

def posture_label(score):
    if score >= 85: return "Excellent"
    if score >= 70: return "Good"
    if score >= 50: return "Fair"
    if score >= 30: return "Poor"
    return "Very Poor"

def draw_skeleton(frame, landmarks, w, h):
    pts = {i: lm_xy(landmarks, i, w, h) for i in
           [NOSE, LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP]}
    for a, b in POSE_CONNECTIONS:
        if a in pts and b in pts:
            cv2.line(frame, (int(pts[a][0]), int(pts[a][1])),
                     (int(pts[b][0]), int(pts[b][1])), (200, 200, 200), 2)
    for _, (x, y) in pts.items():
        cv2.circle(frame, (int(x), int(y)), 5, (0, 255, 180), -1)

# ── Calibration ───────────────────────────────────────────────────────────────

def run_calibration(cap, landmarker, frame_ts_ms=0):
    """
    Countdown then capture CALIB_FRAMES frames, averaged into a reference dict.
    Uses read_frame() so rotation is already applied.
    frame_ts_ms must be passed in and continued from — never reset to 0 —
    because MediaPipe requires monotonically increasing timestamps.
    Returns (reference_dict, frame_ts_ms) or None on failure.
    """

    # Countdown
    countdown_start = time.time()
    while True:
        ret, frame = read_frame(cap)
        if not ret:
            return None
        h, w = frame.shape[:2]

        elapsed   = time.time() - countdown_start
        remaining = max(0, CALIB_COUNTDOWN - int(elapsed))

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.45, frame, 0.55, 0)

        cv2.putText(frame, "CALIBRATION",
                    (w // 2 - 160, h // 2 - 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(frame, "Sit in your best posture and hold still.",
                    (w // 2 - 270, h // 2 - 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (200, 200, 200), 2, cv2.LINE_AA)

        if remaining > 0:
            cv2.putText(frame, str(remaining),
                        (w // 2 - 30, h // 2 + 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 3.0, (0, 220, 255), 5, cv2.LINE_AA)
        else:
            cv2.putText(frame, "Capturing...",
                        (w // 2 - 110, h // 2 + 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 120), 3, cv2.LINE_AA)

        cv2.imshow("Posture Analyzer", frame)
        cv2.waitKey(1)

        if elapsed >= CALIB_COUNTDOWN:
            break

    # Capture
    accumulated = {k: 0.0 for k in
                   ["spine_angle", "ear_forward", "neck_angle",
                    "shoulder_diff", "ear_height_diff"]}
    captured = 0

    while captured < CALIB_FRAMES:
        ret, frame = read_frame(cap)
        if not ret:
            break
        h, w = frame.shape[:2]

        frame_ts_ms += 33
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = Image(image_format=ImageFormat.SRGB, data=rgb)
        result = landmarker.detect_for_video(mp_img, frame_ts_ms)

        if result.pose_landmarks and len(result.pose_landmarks) > 0:
            feats = extract_features(result.pose_landmarks[0], w, h)
            for k in accumulated:
                accumulated[k] += feats[k]
            captured += 1

        progress = int((captured / CALIB_FRAMES) * (w - 80))
        cv2.rectangle(frame, (40, h - 50), (w - 40, h - 20), (60, 60, 60), -1)
        cv2.rectangle(frame, (40, h - 50), (40 + progress, h - 20), (0, 220, 120), -1)
        cv2.putText(frame, f"Capturing reference... {captured}/{CALIB_FRAMES}",
                    (40, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 2)
        cv2.imshow("Posture Analyzer", frame)
        cv2.waitKey(1)

    if captured == 0:
        return None

    reference = {k: accumulated[k] / captured for k in accumulated}
    print("\n✓ Calibration complete.")
    print(f"  spine={reference['spine_angle']:.1f}°  "
          f"neck={reference['neck_angle']:.1f}°  "
          f"ear_fwd={reference['ear_forward']:.1f}  "
          f"shoulder_sym={reference['shoulder_diff']:.1f}\n")
    return reference, frame_ts_ms

# ── Phone tracker ─────────────────────────────────────────────────────────────

class PhoneTracker:
    def __init__(self):
        assert PHONE_ALERT_SEC < PHONE_WINDOW_SEC
        self.window_start    = time.time()
        self.phone_seconds   = 0.0
        self.last_tick       = time.time()
        self.phone_visible   = False
        self.alert_triggered = False
        self.violation_count = 0

    def update(self, phone_detected):
        now     = time.time()
        elapsed = now - self.last_tick
        self.last_tick     = now
        self.phone_visible = phone_detected

        if phone_detected:
            self.phone_seconds += elapsed

        if now - self.window_start >= PHONE_WINDOW_SEC:
            pct      = self.phone_seconds / PHONE_WINDOW_SEC * 100
            violated = self.phone_seconds >= PHONE_ALERT_SEC
            if violated:
                self.violation_count += 1
            print(
                f"\n{'='*55}\n"
                f"  📱 PHONE USAGE — {PHONE_WINDOW_SEC}s window summary\n"
                f"     Phone visible: {self.phone_seconds:.0f}s / {PHONE_WINDOW_SEC}s  ({pct:.0f}%)\n"
                + (f"  ⚠️  ALERT: Threshold exceeded!  "
                   f"Total violations: {self.violation_count}\n" if violated else "")
                + f"{'='*55}\n"
            )
            self.window_start    = now
            self.phone_seconds   = 0.0
            self.alert_triggered = False

        if self.phone_seconds >= PHONE_ALERT_SEC and not self.alert_triggered:
            self.alert_triggered = True
            remaining = PHONE_WINDOW_SEC - (now - self.window_start)
            print(f"  ⚠️  PHONE ALERT: visible {self.phone_seconds:.0f}s this window "
                  f"({remaining:.0f}s remaining)  |  "
                  f"Total violations so far: {self.violation_count}")

    def status_str(self):
        remaining = max(0, PHONE_WINDOW_SEC - (time.time() - self.window_start))
        return (
            f"Phone: {'YES' if self.phone_visible else 'no ':3s}  "
            f"| {self.phone_seconds:.0f}s/{PHONE_WINDOW_SEC}s  "
            f"| resets in {remaining:.0f}s  "
            f"| violations: {self.violation_count}"
        )

# ── Posture strike tracker ────────────────────────────────────────────────────

class PostureStrikeTracker:
    def __init__(self):
        self.bad_since       = None
        self.bad_streak_secs = 0.0
        self.warn_issued     = False
        self.strike_issued   = False
        self.strike_count    = 0

    def update(self, score):
        now    = time.time()
        is_bad = score < 70

        if is_bad:
            if self.bad_since is None:
                self.bad_since = now
            self.bad_streak_secs = now - self.bad_since

            if self.bad_streak_secs >= POSTURE_WARN_SEC and not self.warn_issued:
                self.warn_issued = True
                print(f"\n  ⚠️  POSTURE WARNING: sub-Good posture held for "
                      f"{self.bad_streak_secs:.0f}s  |  strikes: {self.strike_count}")

            if self.bad_streak_secs >= POSTURE_STRIKE_SEC and not self.strike_issued:
                self.strike_issued = True
                self.strike_count += 1
                print(f"\n  🚨 POSTURE STRIKE #{self.strike_count}: sub-Good posture held for "
                      f"{self.bad_streak_secs:.0f}s — sit up!")
        else:
            self.bad_since       = None
            self.bad_streak_secs = 0.0
            self.warn_issued     = False
            self.strike_issued   = False

    def status_str(self):
        if self.bad_since is None:
            return f"posture OK  | strikes: {self.strike_count}"
        return (
            f"bad posture: {self.bad_streak_secs:.0f}s"
            + (" ⚠" if self.warn_issued and not self.strike_issued else "")
            + (" 🚨" if self.strike_issued else "")
            + f"  | strikes: {self.strike_count}"
        )

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    for path, name in [(POSE_MODEL, "pose_landmarker.task"),
                       (DETECTOR_MODEL, "object_detector.tflite")]:
        if not os.path.exists(path):
            print(f"[ERROR] Missing model file: {path}")
            if name == "pose_landmarker.task":
                print("  curl -o pose_landmarker.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task")
            else:
                print("  curl -o object_detector.tflite https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/latest/efficientdet_lite0.tflite")
            return

    pose_options = mp_vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(
            model_asset_path=POSE_MODEL,
            delegate=mp_python.BaseOptions.Delegate.CPU),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.6,
        min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )

    det_options = mp_vision.ObjectDetectorOptions(
        base_options=mp_python.BaseOptions(
            model_asset_path=DETECTOR_MODEL,
            delegate=mp_python.BaseOptions.Delegate.CPU),
        running_mode=mp_vision.RunningMode.VIDEO,
        score_threshold=0.4,
        max_results=10,
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Could not open camera (index 0). Try 1 or 2.")
        return

    print("=== Posture Analyzer ===")
    print(f"Phone alert: >= {PHONE_ALERT_SEC}s visible in any {PHONE_WINDOW_SEC}s window.")
    print(f"Posture warning at {POSTURE_WARN_SEC}s sub-Good, strike at {POSTURE_STRIKE_SEC}s.")
    print("SPACE = calibrate   S = skip   R = recalibrate   Q = quit\n")

    SMOOTH_N       = 15
    score_buffer   = []
    last_print     = 0.0
    PRINT_INTERVAL = 1.0
    frame_ts_ms    = 0
    reference      = None
    phone_tracker  = PhoneTracker()
    posture_strike = PostureStrikeTracker()

    with mp_vision.PoseLandmarker.create_from_options(pose_options) as landmarker, \
         mp_vision.ObjectDetector.create_from_options(det_options) as detector:

        # ── Startup: calibrate or skip ────────────────────────────────────────
        while True:
            ret, frame = read_frame(cap)
            if not ret:
                break
            h, w = frame.shape[:2]
            cv2.putText(frame, "SPACE = calibrate   S = skip", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, "Sit in good posture before pressing SPACE.",
                        (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 180, 180), 2, cv2.LINE_AA)
            cv2.imshow("Posture Analyzer", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(' '):
                result = run_calibration(cap, landmarker, frame_ts_ms)
                if result is not None:
                    reference, frame_ts_ms = result
                break
            elif key in (ord('s'), ord('S')):
                print("Skipping calibration — absolute geometry scoring only.\n")
                break
            elif key in (ord('q'), ord('Q')):
                cap.release()
                cv2.destroyAllWindows()
                return

        # ── Main loop ─────────────────────────────────────────────────────────
        print("Running. Press R to recalibrate, Q to quit.\n")
        while True:
            ret, frame = read_frame(cap)
            if not ret:
                print("[ERROR] Failed to read frame.")
                break

            h, w   = frame.shape[:2]
            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = Image(image_format=ImageFormat.SRGB, data=rgb)
            frame_ts_ms += 33

            pose_result = landmarker.detect_for_video(mp_img, frame_ts_ms)
            det_result  = detector.detect_for_video(mp_img, frame_ts_ms)

            # ── Phone detection ───────────────────────────────────────────────
            phone_detected = False
            phone_boxes    = []
            for detection in det_result.detections:
                for cat in detection.categories:
                    if "cell phone" in cat.category_name.lower():
                        phone_detected = True
                        bb = detection.bounding_box
                        phone_boxes.append((bb.origin_x, bb.origin_y,
                                            bb.width, bb.height, cat.score))
            phone_tracker.update(phone_detected)

            for (x, y, bw, bh, conf) in phone_boxes:
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 100, 255), 2)
                cv2.putText(frame, f"Phone {conf:.0%}", (x, max(y - 8, 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 100, 255), 2)

            # ── Posture scoring ───────────────────────────────────────────────
            if pose_result.pose_landmarks and len(pose_result.pose_landmarks) > 0:
                landmarks = pose_result.pose_landmarks[0]
                try:
                    score, metrics = analyze_posture(landmarks, w, h, reference)
                except Exception:
                    score = None

                if score is not None:
                    score_buffer.append(score)
                    if len(score_buffer) > SMOOTH_N:
                        score_buffer.pop(0)
                    smoothed = round(sum(score_buffer) / len(score_buffer), 1)
                    label    = posture_label(smoothed)

                    posture_strike.update(smoothed)

                    now = time.time()
                    if now - last_print >= PRINT_INTERVAL:
                        last_print = now
                        mode_tag = "[ref+abs]" if reference else "[abs only]"
                        print(
                            f"Posture: {smoothed:5.1f}/100 [{label:9s}] {mode_tag}"
                            f"  spine={metrics['spine_angle_deg']}°"
                            f"  neck={metrics['neck_angle_deg']}°"
                            f"  fwd={metrics['ear_forward_norm']}"
                            f"  |  {posture_strike.status_str()}"
                            f"  |  {phone_tracker.status_str()}"
                        )

                    color = (
                        (0, 200, 0)   if smoothed >= 70 else
                        (0, 165, 255) if smoothed >= 50 else
                        (0, 0, 220)
                    )
                    mode_label = "ref+abs" if reference else "abs only"
                    cv2.putText(frame, f"Posture: {smoothed}/100  {label}  ({mode_label})",
                                (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA)

                draw_skeleton(frame, landmarks, w, h)
            else:
                cv2.putText(frame, "No person detected", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (100, 100, 255), 2, cv2.LINE_AA)

            # ── Posture strike overlay ────────────────────────────────────────
            if posture_strike.bad_since is not None:
                streak = posture_strike.bad_streak_secs
                if posture_strike.strike_issued:
                    ps_color = (0, 0, 220)
                    ps_text  = f"POSTURE STRIKE #{posture_strike.strike_count}  ({streak:.0f}s)"
                elif posture_strike.warn_issued:
                    ps_color = (0, 140, 255)
                    ps_text  = f"POSTURE WARNING  ({streak:.0f}s / {POSTURE_STRIKE_SEC}s)"
                else:
                    ps_color = (0, 200, 220)
                    ps_text  = f"sub-Good: {streak:.0f}s / {POSTURE_WARN_SEC}s"
                cv2.putText(frame, ps_text, (20, 75),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, ps_color, 2, cv2.LINE_AA)

            cv2.putText(frame, f"Posture strikes: {posture_strike.strike_count}",
                        (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1, cv2.LINE_AA)

            # ── Phone overlay ─────────────────────────────────────────────────
            remaining   = max(0, PHONE_WINDOW_SEC - (time.time() - phone_tracker.window_start))
            phone_color = (0, 100, 255) if phone_detected else (180, 180, 180)
            cv2.putText(frame,
                        f"Phone: {phone_tracker.phone_seconds:.0f}s/{PHONE_WINDOW_SEC}s "
                        f"(resets in {remaining:.0f}s)",
                        (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.65, phone_color, 2, cv2.LINE_AA)

            if phone_tracker.alert_triggered:
                cv2.putText(frame,
                            f"!! PHONE ALERT  (violations: {phone_tracker.violation_count})",
                            (20, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 60, 255), 2, cv2.LINE_AA)

            # ── Hint bar ──────────────────────────────────────────────────────
            cv2.putText(frame, "R = recalibrate   Q = quit",
                        (20, h - 15), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (120, 120, 120), 1, cv2.LINE_AA)

            cv2.imshow("Posture Analyzer", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key in (ord("r"), ord("R")):
                print("\nRecalibrating...")
                score_buffer.clear()
                posture_strike = PostureStrikeTracker()
                result = run_calibration(cap, landmarker, frame_ts_ms)
                if result is not None:
                    reference, frame_ts_ms = result
                else:
                    print("[WARN] Recalibration failed — keeping previous reference.")

    cap.release()
    cv2.destroyAllWindows()
    print("\nSession ended.")

if __name__ == "__main__":
    main()