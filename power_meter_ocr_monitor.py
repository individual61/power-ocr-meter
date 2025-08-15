#!/usr/bin/env python3
import argparse
import csv
import cv2
import math
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from picamera2 import Picamera2

try:
    cv2.setUseOptimized(True)  # usually already True, but explicit is fine
    cv2.setNumThreads(1)       # keep CPU usage predictable (good for Pi/Zero 2 W)
except Exception:
    pass

# ============================================================
# CLI
# ============================================================

def parse_args():
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

    # Persist LiFePO4wered policy to flash (CFG_WRITE 0x46)
    p.add_argument("--lp4w-persist", action="store_true",
                   help="Persist LiFePO4wered policy to flash (use with care).")

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

# ============================================================
# LiFePO4wered integration
# ============================================================

LP4W_AVAILABLE = False
try:
    # Python binding from https://github.com/xorbit/LiFePO4wered-Pi
    from lifepo4wered import (
        read_lifepo4wered, write_lifepo4wered,
        VBAT, VIN, IOUT,
        AUTO_BOOT, AUTO_SHDN_TIME, VIN_THRESHOLD, CFG_WRITE
    )
    LP4W_AVAILABLE = True
except Exception:
    LP4W_AVAILABLE = False  # we'll fall back to CLI if present

def _cli_get(name: str) -> int:
    out = subprocess.check_output(["lifepo4wered-cli", "get", name], text=True).strip()
    # Some outputs are "NAME = value"; handle both raw and "NAME = X"
    if "=" in out:
        out = out.split("=", 1)[1].strip()
    return int(out)

def _cli_set(name: str, value: int) -> None:
    subprocess.check_call(["lifepo4wered-cli", "set", name, str(value)])

def lp4w_get_vbat_mV() -> int:
    return read_lifepo4wered(VBAT) if LP4W_AVAILABLE else _cli_get("VBAT")

def lp4w_get_vin_mV() -> int:
    return read_lifepo4wered(VIN) if LP4W_AVAILABLE else _cli_get("VIN")

def lp4w_get_iout_mA() -> int:
    return read_lifepo4wered(IOUT) if LP4W_AVAILABLE else _cli_get("IOUT")

def lp4w_set_vin_threshold_mV(value: int, persist: bool):
    if LP4W_AVAILABLE:
        write_lifepo4wered(VIN_THRESHOLD, value)
        if persist:
            write_lifepo4wered(CFG_WRITE, 0x46)
    else:
        _cli_set("VIN_THRESHOLD", value)
        if persist:
            _cli_set("CFG_WRITE", 0x46)

def lp4w_apply_config(delay_minutes: int, auto_boot_mode: int, persist: bool):
    """
    Apply key policy:
      - AUTO_SHDN_TIME: minutes to wait after VIN < threshold before shutdown
      - AUTO_BOOT:      3 = AUTO_BOOT_VIN (boot only when VIN present)
    """
    try:
        if LP4W_AVAILABLE:
            write_lifepo4wered(AUTO_SHDN_TIME, delay_minutes)
            write_lifepo4wered(AUTO_BOOT,      auto_boot_mode)
            if persist:
                write_lifepo4wered(CFG_WRITE, 0x46)
        else:
            _cli_set("AUTO_SHDN_TIME", delay_minutes)
            _cli_set("AUTO_BOOT", auto_boot_mode)
            if persist:
                _cli_set("CFG_WRITE", 0x46)
        return True, None
    except Exception as e:
        return False, str(e)

# ===== Runtime LiFePO4wered Policy (applied each start) =====
LP4W_POLICY = {
    "AUTO_BOOT": 3,            # 3 = AUTO_BOOT_VIN (boot only when VIN present)
    "AUTO_SHDN_TIME": 2,       # minutes to wait after VIN < threshold before shutdown
    "VIN_THRESHOLD_mV": 4500,  # adjust if your PSU/cable sags
    # "VBAT_BOOT_mV": 3150,    # add if you want to override default boot threshold
}
LP4W_PERSIST_DEFAULT = False   # use --lp4w-persist to write to flash

# ============================================================
# Temperature helpers
# ============================================================

def _read_all_thermal_zones():
    """
    Returns {zone_type_lower: temp_C_float}
    Reads /sys/class/thermal/thermal_zone*/{type,temp}; values are in millidegC.
    """
    temps = {}
    base = "/sys/class/thermal"
    try:
        for name in os.listdir(base):
            if not name.startswith("thermal_zone"):
                continue
            tpath = os.path.join(base, name, "type")
            vpath = os.path.join(base, name, "temp")
            try:
                with open(tpath) as f:
                    ttype = f.read().strip().lower()
                with open(vpath) as f:
                    millideg = int(f.read().strip())
                temps[ttype] = millideg / 1000.0
            except Exception:
                continue
    except Exception:
        pass

    # Fallback to vcgencmd for SoC if nothing obvious found
    if not any(k in temps for k in ("cpu-thermal", "soc-thermal", "bcm2835_thermal", "rpi-thermal")):
        try:
            out = subprocess.check_output(["vcgencmd", "measure_temp"], text=True).strip()
            # format: temp=47.3'C
            val = float(out.split("=")[1].split("'")[0])
            temps.setdefault("cpu-thermal", val)
        except Exception:
            pass
    return temps
    
def read_named_temps():
    """
    Returns a tuple (soc_C, rp1_C, pmic_C) where each may be None if unavailable.
    """
    zones = _read_all_thermal_zones()
    # SoC/CPU candidates (first match wins)
    for key in ("cpu-thermal", "soc-thermal", "bcm2835_thermal", "rpi-thermal", "cpu"):
        if key in zones:
            soc = zones[key]
            break
    else:
        soc = None

    # RP1 southbridge (Pi 5)
    rp1 = None
    for k, v in zones.items():
        if "rp1" in k:
            rp1 = v
            break

    # PMIC temperature (name varies; look for 'pmic')
    pmic = None
    for k, v in zones.items():
        if "pmic" in k:
            pmic = v
            break

    return soc, rp1, pmic
    
# ============================================================
# OCR / decoding state
# ============================================================

last_capture_time = 0.0
picam2 = None
window_name = "PiCam Live Preview (press 'q' to quit)"
error_msg = ""
logfile = None
csv_writer = None
RUNNING = True  # toggled by signal handlers

# Global offsets/ROIs
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

MODE_INDICATORS = ["w", "curr", "volt", "freq", "ct", "ec", "pf"]
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

# ============================================================
# Logging
# ============================================================

def _fmt_ts(dt: datetime) -> str:
    # Format: YYYY-MM-DD HH:MM:SS.mmm (ms precision)
    return f"{dt:%Y-%m-%d %H:%M:%S}.{dt.microsecond // 1000:03d}"

def init_logger():
    global logfile, csv_writer
    os.makedirs(LOG_DIR, exist_ok=True)
    fname = datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
    path = os.path.join(LOG_DIR, fname)
    logfile = open(path, "w", newline="")
    csv_writer = csv.writer(logfile)
    # Combined timestamp + power metrics
    csv_writer.writerow(["timestamp", "mode", "value",
                         "vbat_mV", "vin_mV", "iout_mA",
                         "soc_C", "rp1_C", "pmic_C",
                         "error"])
    logfile.flush()
    return logfile, csv_writer

def log_entry(writer, captured_at: datetime, mode, value, error_msg, logfile,
              vbat_mV=None, vin_mV=None, iout_mA=None,
              soc_C=None, rp1_C=None, pmic_C=None):
    ts = _fmt_ts(captured_at)
    writer.writerow([
        ts, mode, f"{value:.4f}",
        "" if vbat_mV is None else vbat_mV,
        "" if vin_mV  is None else vin_mV,
        "" if iout_mA is None else iout_mA,
        "" if soc_C  is None else f"{soc_C:.1f}",
        "" if rp1_C  is None else f"{rp1_C:.1f}",
        "" if pmic_C is None else f"{pmic_C:.1f}",
        error_msg or ""
    ])
    logfile.flush()

# ============================================================
# Image processing helpers
# ============================================================

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

    config = picam2.create_video_configuration(
        main={"size": resolution, "format": "XRGB8888"}  # single stream
    )
    picam2.configure(config)
    picam2.set_controls({"FrameRate": 10})  # lighten ISP load
    picam2.start()
    time.sleep(0.1)
    if preview:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

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
    elapsed = now - last_capture_time
    if elapsed < CAPTURE_INTERVAL:
        # Sleep just enough, but cap it so signals remain responsive
        time.sleep(min(CAPTURE_INTERVAL - elapsed, 0.05))
        return True
    if elapsed >= CAPTURE_INTERVAL:
        # Capture + timestamp (use same timestamp across processing)
        rgb = picam2.capture_array()
        captured_at = datetime.now()
        overlay_ts = _fmt_ts(captured_at)

        frame_clean = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        frame_clean_gr_pre = cv2.cvtColor(frame_clean, cv2.COLOR_BGR2GRAY)
        _, frame_clean_gr = cv2.threshold(frame_clean_gr_pre, 160, 255, cv2.THRESH_BINARY)

        if preview:
            frame_annotated_color = cv2.cvtColor(frame_clean_gr, cv2.COLOR_GRAY2BGR)
            cv2.putText(frame_annotated_color, overlay_ts, (10, 30),
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

        # Read LiFePO4wered telemetry (best effort)
        vbat = vin = iout = None
        try:
            vbat = lp4w_get_vbat_mV()
            vin  = lp4w_get_vin_mV()
            iout = lp4w_get_iout_mA()
        except Exception as e:
            print(f"[LiFePO4wered] read failed: {e}")

        print(f"{mode_str}, {total_value:.4f}")
        log_entry(csv_writer, captured_at, mode_str, total_value, error_msg, logfile,
                  vbat_mV=vbat, vin_mV=vin, iout_mA=iout)
        error_msg = ""

        if preview:
            cv2.imshow(window_name, frame_annotated_color)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                return False

        # Honor the capture interval
        last_capture_time = now

    return True

# ============================================================
# Signals / main
# ============================================================

def _handle_signal(signum, frame):
    global RUNNING
    RUNNING = False

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

def main():
    global logfile, csv_writer
    try:
        setup(resolution=RESOLUTION, framerate=30, preview=args.preview)

        # Apply LiFePO4wered policy at start
        persist = getattr(args, "lp4w_persist", LP4W_PERSIST_DEFAULT)
        ok, err = lp4w_apply_config(
            delay_minutes=LP4W_POLICY["AUTO_SHDN_TIME"],
            auto_boot_mode=LP4W_POLICY["AUTO_BOOT"],
            persist=persist
        )
        if not ok:
            print(f"[LiFePO4wered] policy apply failed: {err}")

        # Set VIN_THRESHOLD (optional but recommended)
        try:
            lp4w_set_vin_threshold_mV(LP4W_POLICY["VIN_THRESHOLD_mV"], persist=persist)
        except Exception as e:
            print(f"[LiFePO4wered] VIN_THRESHOLD set failed: {e}")

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