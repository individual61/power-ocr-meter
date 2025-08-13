#!/usr/bin/env python3
import argparse
import cv2
import time
from picamera2 import Picamera2
from datetime import datetime
import math
import os
import csv
import signal
import sys

### Run with  --no-preview to run headless, with no camera display.

## Steps to install
#Install systemd service to run headless at boot
#sudo nano /etc/systemd/system/power-ocr-meter.service

# Contents:
# [Unit]
# Description=Power OCR Meter (PiCam -> 7-seg -> CSV)
# After=network-online.target
# 
# [Service]
# Type=simple
# User=paulwb
# Group=paulwb
# WorkingDirectory=/home/paulwb/Documents/GitHub/power-ocr-meter
# Environment=PYTHONUNBUFFERED=1
# ExecStartPre=/bin/sleep 5
# ExecStart=/usr/bin/python3 /home/paulwb/Documents/GitHub/power-ocr-meter/power_meter_ocr_monitor.py --no-preview --interval 0.35 --resolution 800x600 --log-dir logs
# Restart=always
# RestartSec=2
# KillSignal=SIGTERM
# TimeoutStopSec=10
# 
# [Install]
# WantedBy=multi-user.target

# To enable and start:

# sudo systemctl daemon-reload
# sudo systemctl enable power-ocr-meter.service
# sudo systemctl start power-ocr-meter.service

# To check logs live:

#journalctl -u power-ocr-meter -f

# To shut down
# sudo systemctl restart power-ocr-meter.service
#sudo systemctl stop power-ocr-meter.service
# sudo systemctl disable power-ocr-meter.service

# -------- CLI --------
def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Power meter OCR logger")

    # Default = preview ON. Use --no-preview to run headless/efficient.
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--preview", dest="preview", action="store_true",
                     help="Show live preview window with overlay (default).")
    grp.add_argument("--no-preview", dest="preview", action="store_false",
                     help="Disable overlay for headless/efficient mode.")
    p.set_defaults(preview=True)

    p.add_argument("--interval", type=float, default=0.35,
                   help="Capture interval in seconds (default: 0.35).")
    p.add_argument("--log-dir", default="logs",
                   help='Directory for CSV logs (default: "logs").')
    p.add_argument("--resolution", default="800x600",
                   help="Camera resolution as WxH (default: 800x600).")
    return p.parse_args()


args = parse_args()

def parse_res(s):
    try:
        w, h = s.lower().split("x")
        return (int(w), int(h))
    except Exception:
        return (800, 600)

CAPTURE_INTERVAL = args.interval
LOG_DIR = args.log_dir
RESOLUTION = parse_res(args.resolution)

# -------- globals --------
last_capture_time = 0.0
picam2 = None
window_name = "PiCam Live Preview (press 'q' to quit)"
error_msg = ""
logfile = None
csv_writer = None
RUNNING = True  # toggled by signal handlers

# Global offsets/ROIs (unchanged from your code)
roi_offs_x = 0
roi_offs_y = 0
roi_watt = (22, 196, 112, 232)
roi_curr = (22, 237, 93, 276)
roi_volt = (22, 280, 107, 317)
roi_freq = (22, 367, 111, 401)
roi_ct   = (112, 68, 178, 117)
roi_ec   = (418, 73, 485, 125)
roi_pf   = (151, 132, 210, 177)
array_of_mode_rois = [roi_watt, roi_curr, roi_volt, roi_freq, roi_ct, roi_ec, roi_pf]

digit_width = 115
digit_height = 200
roi_digit1 = (115, 200, 115 + digit_width, 207 + digit_height)
roi_digit2 = (236, 200, 236 + digit_width, 207 + digit_height)
roi_digit3 = (361, 200, 361 + digit_width, 207 + digit_height)
roi_digit4 = (491, 200, 491 + digit_width, 209 + digit_height)
roi_digit5 = (618, 200, 618 + digit_width, 210 + digit_height)
array_of_digit_rois = [roi_digit1, roi_digit2, roi_digit3, roi_digit4, roi_digit5]

dot_width = 24
dot_height = 24
roi_dot2 = (341, 378, 341 + dot_width, 378 + dot_height)
roi_dot3 = (464, 379, 464 + dot_width, 379 + dot_height)
roi_dot4 = (592, 382, 592 + dot_width, 382 + dot_height)
array_of_dot_rois = [roi_dot2, roi_dot3, roi_dot4]

MODE_INDICATORS = ["watt", "curr", "volt", "freq", "ct", "ec", "pf"]
SEGMENT_NAMES = ["a", "b", "c", "d", "e", "f", "g"]
DOT_NAMES = ["0.001", "0.01", "0.1"]
DIGIT_NAMES = ["1E4", "1E3", "1E2", "1E1", "1E0"]

lcd_state = {
    "digits": { name: { seg: False for seg in SEGMENT_NAMES } for name in DIGIT_NAMES },
    "dots":   { name: False for name in DOT_NAMES },
    "modes":  { mode: False for mode in MODE_INDICATORS }
}

SEGMENT_DIGIT_MAP = {
    frozenset(): 0,
    frozenset(["a","b","c","d","e","f"]): 0,
    frozenset(["b","c"]): 1,
    frozenset(["a","b","g","e","d"]): 2,
    frozenset(["a","b","c","d","g"]): 3,
    frozenset(["f","g","b","c"]): 4,
    frozenset(["a","f","g","c","d"]): 5,
    frozenset(["a","f","e","d","c","g"]): 6,
    frozenset(["a","b","c"]): 7,
    frozenset(["a","b","c","d","e","f","g"]): 8,
    frozenset(["a","b","c","d","f","g"]): 9,
}

def init_logger():
    global logfile, csv_writer
    os.makedirs(LOG_DIR, exist_ok=True)
    fname = datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
    path = os.path.join(LOG_DIR, fname)
    logfile = open(path, "w", newline="")
    csv_writer = csv.writer(logfile)
    csv_writer.writerow(["date", "time", "mode", "value", "error"])
    logfile.flush()
    return logfile, csv_writer

def log_entry(writer, mode, value, error_msg, logfile):
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    tenth = now.microsecond // 100000
    time_str = f"{now:%H:%M:%S}.{tenth}"
    writer.writerow([date_str, time_str, mode, f"{value:.4f}", error_msg or ""])
    logfile.flush()

def decode_digit(segments: dict[str, bool]) -> int | None:
    global error_msg
    on_segments = { seg for seg, lit in segments.items() if lit }
    digit = SEGMENT_DIGIT_MAP.get(frozenset(on_segments))
    if digit is None:
        error = f"Warning: decode_digit got unrecognized segment pattern: {sorted(on_segments)}"
        error_msg = (error_msg + " | " if error_msg else "") + error
        print(error)
    return digit

def evaluate_roi(frame_thresh, roi_tuple, on_threshold=50):
    x1, y1, x2, y2 = roi_tuple
    roi_image = frame_thresh[y1:y2, x1:x2]
    white_pixels = cv2.countNonZero(roi_image)
    total_pixels = roi_image.shape[0] * roi_image.shape[1]
    black_pixels = float(total_pixels) - white_pixels
    return black_pixels >= on_threshold

def get_digit_sub_roi(digit_roi):
    dx1, dy1, dx2, dy2 = digit_roi
    x_middle = dx1 + (dx2 - dx1)/2.0
    y_middle = dy1 + (dy2 - dy1)/2.0
    short_size = 20
    long_size = 40
    offset_lateral = 36
    y_seg_offset_top = -80
    y_seg_offset_side_top = -42
    y_seg_offset_side_bott = 46
    y_seg_offset_bott = 87
    roi_top =  (math.floor(x_middle - short_size/2), math.floor(y_middle + y_seg_offset_top - long_size/2),
                math.floor(x_middle + short_size/2), math.floor(y_middle + y_seg_offset_top + long_size/2))
    roi_bott = (math.floor(x_middle - short_size/2), math.floor(y_middle + y_seg_offset_bott - long_size/2),
                math.floor(x_middle + short_size/2), math.floor(y_middle + y_seg_offset_bott + long_size/2))
    roi_midd = (math.floor(x_middle - short_size/2), math.floor(y_middle  - long_size/2),
                math.floor(x_middle + short_size/2), math.floor(y_middle + long_size/2))
    roi_tl =  (math.floor(x_middle - offset_lateral - long_size/2), math.floor(y_middle + y_seg_offset_side_top - short_size/2),
                math.floor(x_middle - offset_lateral + long_size/2), math.floor(y_middle + y_seg_offset_side_top + short_size/2))
    roi_tr =  (math.floor(x_middle + offset_lateral - long_size/2), math.floor(y_middle + y_seg_offset_side_top - short_size/2),
                math.floor(x_middle + offset_lateral + long_size/2), math.floor(y_middle + y_seg_offset_side_top + short_size/2))
    roi_bl =  (math.floor(x_middle - offset_lateral - long_size/2), math.floor(y_middle + y_seg_offset_side_bott - short_size/2),
                math.floor(x_middle - offset_lateral + long_size/2), math.floor(y_middle + y_seg_offset_side_bott + short_size/2))
    roi_br =  (math.floor(x_middle + offset_lateral - long_size/2), math.floor(y_middle + y_seg_offset_side_bott - short_size/2),
                math.floor(x_middle + offset_lateral + long_size/2), math.floor(y_middle + y_seg_offset_side_bott + short_size/2))
    return (roi_top, roi_tr, roi_br, roi_bott, roi_bl, roi_tl, roi_midd)

def setup(resolution=(640, 480), framerate=30, preview=False):
    global last_capture_time, picam2
    last_capture_time = time.time() - CAPTURE_INTERVAL

    picam2 = Picamera2()

    # No built-in preview; rely on OpenCV window only
    config = picam2.create_preview_configuration(
        main={"size": resolution},
        lores={"size": resolution}
        # note: intentionally NO display="main"
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(0.1)

    if preview:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)  # WINDOW_NORMAL plays nicer over NX

def compute_dot_multiplier(dots: dict[str, bool]) -> float:
    # priority: 0.1, 0.01, 0.001; default 1.0
    if dots["0.1"]:
        return 0.1
    if dots["0.01"]:
        return 0.01
    if dots["0.001"]:
        return 0.001
    return 1.0

def loop(preview=False):
    global csv_writer, logfile, error_msg, last_capture_time
    now = time.time()
    if now - last_capture_time >= CAPTURE_INTERVAL:
        rgb = picam2.capture_array()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        frame_clean = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        frame_clean_gr_pre = cv2.cvtColor(frame_clean, cv2.COLOR_BGR2GRAY)
        _, frame_clean_gr = cv2.threshold(frame_clean_gr_pre, 160, 255, cv2.THRESH_BINARY)

        if preview:
            frame_annotated_color = cv2.cvtColor(frame_clean_gr, cv2.COLOR_GRAY2BGR)
            cv2.putText(frame_annotated_color, timestamp, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 1, cv2.LINE_AA)

        # Dots
        for dot_name, dot_roi in zip(DOT_NAMES, array_of_dot_rois):
            if preview:
                x1, y1, x2, y2 = dot_roi
                cv2.rectangle(frame_annotated_color, (x1 + roi_offs_x, y1 + roi_offs_y),
                              (x2 + roi_offs_x, y2 + roi_offs_y), (255, 0, 0), 1)
            roi_status = evaluate_roi(frame_clean_gr, dot_roi, on_threshold=100)
            lcd_state["dots"][dot_name] = roi_status
            if preview and roi_status:
                x1, y1, x2, y2 = dot_roi
                cv2.rectangle(frame_annotated_color, (x2 + roi_offs_x - 5, y2 + roi_offs_y - 5),
                              (x2 + roi_offs_x, y2 + roi_offs_y), (0, 0, 255), -1)

        # Modes
        for mode_name, mode_roi in zip(MODE_INDICATORS, array_of_mode_rois):
            if preview:
                x1, y1, x2, y2 = mode_roi
                cv2.rectangle(frame_annotated_color, (x1 + roi_offs_x, y1 + roi_offs_y),
                              (x2 + roi_offs_x, y2 + roi_offs_y), (0, 255, 0), 1)
            roi_status = evaluate_roi(frame_clean_gr, mode_roi, on_threshold=100)
            lcd_state["modes"][mode_name] = roi_status
            if preview and roi_status:
                x1, y1, x2, y2 = mode_roi
                cv2.rectangle(frame_annotated_color, (x2 + roi_offs_x - 5, y2 + roi_offs_y - 5),
                              (x2 + roi_offs_x, y2 + roi_offs_y), (0, 0, 255), -1)

        # Digits
        for digit_name, digit_roi in zip(DIGIT_NAMES, array_of_digit_rois):
            if preview:
                x1, y1, x2, y2 = digit_roi
                cv2.rectangle(frame_annotated_color, (x1 + roi_offs_x, y1 + roi_offs_y),
                              (x2 + roi_offs_x, y2 + roi_offs_y), (0, 0, 255), 1)
            segment_rois = get_digit_sub_roi(digit_roi)
            for seg_name, segment_roi in zip(SEGMENT_NAMES, segment_rois):
                if preview:
                    sx1, sy1, sx2, sy2 = segment_roi
                    cv2.rectangle(frame_annotated_color, (sx1 + roi_offs_x, sy1 + roi_offs_y),
                                  (sx2 + roi_offs_x, sy2 + roi_offs_y), (255, 0, 255), 1)
                roi_status = evaluate_roi(frame_clean_gr, segment_roi, on_threshold=100)
                lcd_state["digits"][digit_name][seg_name] = roi_status
                if preview and roi_status:
                    sx1, sy1, sx2, sy2 = segment_roi
                    cv2.rectangle(frame_annotated_color, (sx2 + roi_offs_x - 5, sy2 + roi_offs_y - 5),
                                  (sx2 + roi_offs_x, sy2 + roi_offs_y), (0, 0, 255), -1)

        # Decode number
        digit_values = [decode_digit(lcd_state["digits"][name]) for name in DIGIT_NAMES]
        if any(v is None for v in digit_values):
            print("Warning: one or more segments failed to decode:", digit_values)
            total_value = 0.0
        else:
            d4, d3, d2, d1, d0 = digit_values
            dot_multiplier = compute_dot_multiplier(lcd_state["dots"])
            total_value = (d4*10000 + d3*1000 + d2*100 + d1*10 + d0) * dot_multiplier

        active_modes = [mode for mode, on in lcd_state["modes"].items() if on]
        mode_str = "+".join(active_modes) if active_modes else "unknown"

        print(f"{mode_str}, {total_value:.4f}")
        log_entry(csv_writer, mode_str, total_value, error_msg, logfile)
        error_msg = ""

        if preview:
            cv2.imshow(window_name, frame_annotated_color)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                return False

    return True

# -------- signals --------
def _handle_signal(signum, frame):
    global RUNNING
    RUNNING = False

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

def main():
    global logfile, csv_writer
    try:
        setup(resolution=RESOLUTION, framerate=30, preview=args.preview)
        logfile, csv_writer = init_logger()
        while RUNNING and loop(preview=args.preview):
            pass
    finally:
        try:
            if picam2 is not None:
                picam2.stop()
        except Exception:
            pass
        if args.preview:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        try:
            if logfile is not None:
                logfile.close()
        except Exception:
            pass

if __name__ == "__main__":
    sys.exit(main() or 0)
