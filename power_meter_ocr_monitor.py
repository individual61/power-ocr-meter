#!/usr/bin/env python3

import cv2
import time
from picamera2 import Picamera2
from datetime import datetime
import math

# Global handles (so both setup() and loop() can see them)
picam2 = None
window_name = "PiCam Live Preview (press 'q' to quit)"

# Global offsets
roi_offs_x = 0
roi_offs_y = 0
roi_watt = (22, 196, 112, 232)
roi_curr = (22, 237, 93, 276)
roi_volt = (22, 280, 107, 317)
roi_freq = (22, 367, 111, 401)
roi_ct =   (112, 68, 178, 117)
roi_ec =   (418, 73, 485, 125)
roi_pf =   (151, 132, 210, 177)


array_of_mode_rois = [roi_watt, roi_curr, roi_volt, roi_freq, roi_ct, roi_ec, roi_pf]

digit_width = 115
digit_height = 200
roi_digit1 = (121, 200, 121 + digit_width, 207 + digit_height)
roi_digit2 = (236, 200, 236 + digit_width, 207 + digit_height)
roi_digit3 = (361, 200, 361 + digit_width, 207 + digit_height)
roi_digit4 = (491, 200, 491 + digit_width, 209 + digit_height)
roi_digit5 = (618, 200, 618 + digit_width, 210 + digit_height)
array_of_digit_rois = [roi_digit1, roi_digit2, roi_digit3, roi_digit4, roi_digit5]

dot_width = 24
dot_height = 24
#roi_dot1 =   (221, 380, 221 + dot_width, 380 + dot_height)
roi_dot2 =   (341, 378, 341 + dot_width, 378 + dot_height)
roi_dot3 =   (464, 379, 464 + dot_width, 379 + dot_height)
roi_dot4 =   (592, 382, 592 + dot_width, 382 + dot_height)
array_of_dot_rois = [roi_dot2, roi_dot3, roi_dot4]



roi_watt = (22, 196, 112, 232)
roi_curr = (22, 237, 93, 276)
roi_volt = (22, 280, 107, 317)
roi_freq = (22, 367, 111, 401)
roi_ct =   (112, 68, 178, 117)
roi_ec =   (418, 73, 485, 125)
roi_pf =   (151, 132, 210, 177)


MODE_INDICATORS = ["watt", "curr", "volt",  "freq", "ct", "ec", "pf"]
SEGMENT_NAMES = ["a", "b", "c", "d", "e", "f", "g"]
DOT_NAMES = ["0.001", "0.01", "0.1"]
DIGIT_NAMES = ["1E4", "1E3", "1E2", "1E1", "1E0"]

lcd_state = {
    # map each digit name → its 7-segment state
    "digits": {
        name: { seg: False for seg in SEGMENT_NAMES }
        for name in DIGIT_NAMES
    },
    # map each dot name → on/off
    "dots": {
        name: False
        for name in DOT_NAMES
    },
    # map each mode indicator → on/off
    "modes": {
        mode: False
        for mode in MODE_INDICATORS
    }
}

SEGMENT_DIGIT_MAP = {
    frozenset(["a","b","c","d","e","f"]):               0,
    frozenset(["b","c"]):                               1,
    frozenset(["a","b","g","e","d"]):                   2,
    frozenset(["a","b","c","d","g"]):                   3,
    frozenset(["f","g","b","c"]):                       4,
    frozenset(["a","f","g","c","d"]):                   5,
    frozenset(["a","f","e","d","c","g"]):               6,
    frozenset(["a","b","c"]):                           7,
    frozenset(["a","b","c","d","e","f","g"]):           8,
    frozenset(["a","b","c","d","f","g"]):               9,
}

def decode_digit(segments: dict[str, bool]) -> int | None:
    """
    Given a dict mapping segment names ("a"–"g") to booleans,
    return the integer 0–9 that those segments form, or None
    if the pattern is unrecognized.
    """
    # collect which segments are "on"
    on_segments = { seg for seg, lit in segments.items() if lit }
    # look up in our map
    digit = SEGMENT_DIGIT_MAP.get(frozenset(on_segments))
    if digit is None:
        # sorted(...) just makes the output deterministic/orderly
        print(f"Warning: decode_digit got unrecognized segment pattern: {sorted(on_segments)}")
    return digit

def evaluate_roi(frame_thresh, roi_tuple, on_threshold=50):
    x1, y1, x2, y2 = roi_tuple
    roi_image = frame_thresh[y1:y2, x1:x2]
    
    # count white pixels (value==255)
    white_pixels = cv2.countNonZero(roi_image)
    total_pixels = roi_image.shape[0] * roi_image.shape[1]
    
    # compute ratio
    black_pixels = (float(total_pixels) - white_pixels)
    
    # optional: for debugging, show ratio on the ROI window
    # cv2.imshow("Segment ROI", roi)

    return_value = black_pixels >= on_threshold
    
    #print(f"ROI {roi_tuple} black: {black_pixels:.2f} >= {on_threshold:.2f} --> {return_value}")
    
    cv2.imshow("Extracted Segment", roi_image)
    cv2.waitKey(1)
    
    
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
    
    roi_top = ( math.floor(x_middle - short_size/2),
                math.floor(y_middle + y_seg_offset_top - long_size/2),
                math.floor(x_middle + short_size/2),
                math.floor(y_middle + y_seg_offset_top + long_size/2))
    
    roi_bott = ( math.floor(x_middle - short_size/2),
                math.floor(y_middle + y_seg_offset_bott - long_size/2),
                math.floor(x_middle + short_size/2),
                math.floor(y_middle + y_seg_offset_bott + long_size/2))
    
    roi_midd = ( math.floor(x_middle - short_size/2),
                math.floor(y_middle  - long_size/2),
                math.floor(x_middle + short_size/2),
                math.floor(y_middle + long_size/2))
    
    roi_tl =  ( math.floor(x_middle - offset_lateral - long_size/2),
                math.floor(y_middle + y_seg_offset_side_top - short_size/2),
                math.floor(x_middle - offset_lateral + long_size/2),
                math.floor(y_middle + y_seg_offset_side_top + short_size/2))
    
    roi_tr =  ( math.floor(x_middle + offset_lateral - long_size/2),
                math.floor(y_middle + y_seg_offset_side_top - short_size/2),
                math.floor(x_middle + offset_lateral + long_size/2),
                math.floor(y_middle + y_seg_offset_side_top + short_size/2))
    
    roi_bl =  ( math.floor(x_middle - offset_lateral - long_size/2),
                math.floor(y_middle + y_seg_offset_side_bott - short_size/2),
                math.floor(x_middle - offset_lateral + long_size/2),
                math.floor(y_middle + y_seg_offset_side_bott + short_size/2))
    
    roi_br =  ( math.floor(x_middle + offset_lateral - long_size/2),
                math.floor(y_middle + y_seg_offset_side_bott - short_size/2),
                math.floor(x_middle + offset_lateral + long_size/2),
                math.floor(y_middle + y_seg_offset_side_bott + short_size/2))
        
    #print(roi_top, roi_bott)
    return (roi_top, roi_tr, roi_br, roi_bott, roi_bl, roi_tl, roi_midd)

def setup(resolution=(640, 480), framerate=30):
    """
    Configure and start the camera, create the display window.
    """
    global picam2
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": resolution},
        lores={"size": resolution},
        display="main"
    )
    picam2.configure(config)
    picam2.start()
    # give the sensor a moment to adjust
    time.sleep(0.1)

    # create the OpenCV window once
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    
    
    

frame_clean_gr_prev = None
#frame_clean_gr = None


def loop():

    """
    Grabs a frame, shows it, and returns False if we should exit.
    Extend this with your future processing steps.
    """
    

    # Capture
    
    rgb = picam2.capture_array()
    time_now = time.time()
    
    # Convert for OpenCV
    
    frame_clean = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    frame_clean_gr_pre_thresh = cv2.cvtColor(frame_clean, cv2.COLOR_BGR2GRAY)
    
    _, frame_clean_gr = cv2.threshold( frame_clean_gr_pre_thresh,    # source image
                                        160,               # threshold value (tweak as needed)
                                        255,               # max value for pixels above threshold
                                        cv2.THRESH_BINARY  # type of thresholding
    )
    
    #############################################################
    # Optional block to measure LCD update rate. Very likely 0.8 seconds, or 0.734.
    if False:
        global frame_clean_gr_prev
        global time_last
        if frame_clean_gr_prev is None:
            frame_clean_gr_prev = frame_clean_gr.copy()
            time_last = time_now
        
        diff = cv2.absdiff(frame_clean_gr_prev, frame_clean_gr)
        _, mask = cv2.threshold(diff, 55, 255, cv2.THRESH_BINARY)
        num_pixels_changed = cv2.countNonZero(mask)
        if num_pixels_changed > 1000:
            delta_t = time_now - time_last
            print(f"Display updated after {delta_t:.3f}s, {num_pixels_changed: 3f}")
            time_last = time_now
        
        frame_clean_gr_prev = frame_clean_gr
        
        #frame_clean_th_previous = frame_clean_th.copy()
        #frame_annotated = frame_clean_gr.copy()
        #frame_annotated = diff.copy()
        frame_annotated = mask.copy()
    ###############################################################
        
    frame_annotated = frame_clean_gr.copy()
    frame_annotated_color = cv2.cvtColor(frame_annotated,cv2.COLOR_GRAY2BGR)
    
    ##### Annotate frame with date
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    
    # args: image, text, org (x,y), font, fontScale, color (BGR), thickness, lineType
    cv2.putText(
        frame_annotated_color,
        timestamp,
        (10, 30),                             # position in pixels from top-left
        cv2.FONT_HERSHEY_SIMPLEX,             # font face
        0.6,                                  # font scale (size)
        (0, 200, 0),                   # font color (white)
        1,                                    # thickness
        cv2.LINE_AA                           # anti-aliased line
    )

    ### Draw colored ROI boxes for all ROIs
    
    ########### DOTS
    for dot_name, dot_roi in zip(DOT_NAMES, array_of_dot_rois):
        x1, y1, x2, y2 = dot_roi
        cv2.rectangle(
            frame_annotated_color,
            (x1 + roi_offs_x, y1 + roi_offs_y),
            (x2 + roi_offs_x, y2 + roi_offs_y),
            (255, 0, 0),
            1
            )
        roi_status = evaluate_roi(frame_clean_gr, dot_roi, on_threshold=100)
        lcd_state["dots"][dot_name] = roi_status
        
        #print(f"ROI {segment_roi} status: {roi_status}")
        if roi_status is True:
            cv2.rectangle(
                frame_annotated_color,
                (x2 + roi_offs_x - 5, y2 + roi_offs_y - 5),
                (x2 + roi_offs_x, y2 + roi_offs_y),
                (0, 0, 255),
                -1
                )
            
    ########### MODES    
    for mode_name, mode_roi in zip(MODE_INDICATORS, array_of_mode_rois):
        x1, y1, x2, y2 = mode_roi
        cv2.rectangle(
            frame_annotated_color,
            (x1 + roi_offs_x, y1 + roi_offs_y),
            (x2 + roi_offs_x, y2 + roi_offs_y),
            (0, 255, 0),
            1
            )
        roi_status = evaluate_roi(frame_clean_gr, mode_roi, on_threshold=100)
        lcd_state["modes"][mode_name] = roi_status
        
        #print(f"ROI {segment_roi} status: {roi_status}")
        if roi_status is True:
            cv2.rectangle(
                frame_annotated_color,
                (x2 + roi_offs_x - 5, y2 + roi_offs_y - 5),
                (x2 + roi_offs_x, y2 + roi_offs_y),
                (0, 0, 255),
                -1
                )
            
    ########### DIGITS
    for digit_name, digit_roi in zip(DIGIT_NAMES, array_of_digit_rois):
        x1, y1, x2, y2 = digit_roi
        cv2.rectangle(
            frame_annotated_color,
            (x1 + roi_offs_x, y1 + roi_offs_y),
            (x2 + roi_offs_x, y2 + roi_offs_y),
            (0, 0, 255),
            1
            )
        
        segment_rois = get_digit_sub_roi(digit_roi)
        
        for seg_name, segment_roi in zip(SEGMENT_NAMES, segment_rois):
            #print(segment_roi)
            sx1, sy1, sx2, sy2 = segment_roi
            cv2.rectangle(
                frame_annotated_color,
                (sx1 + roi_offs_x, sy1 + roi_offs_y),
                (sx2 + roi_offs_x, sy2 + roi_offs_y),
                (255, 0, 255),
                1
                )
            
            roi_status = evaluate_roi(frame_clean_gr, segment_roi, on_threshold=100)
            lcd_state["digits"][digit_name][seg_name] = roi_status
            
            #print(f"ROI {segment_roi} status: {roi_status}")
            if roi_status is True:
                cv2.rectangle(
                    frame_annotated_color,
                    (sx2 + roi_offs_x - 5, sy2 + roi_offs_y - 5),
                    (sx2 + roi_offs_x, sy2 + roi_offs_y),
                    (0, 0, 255),
                    -1
                    )   

    #array_of_mode_rois = [roi_watt, roi_curr, roi_volt, roi_freq, roi_ct, roi_ec, roi_pf]
    #array_of_digit_rois = [roi_digit1, roi_digit2, roi_digit3, roi_digit4, roi_digit5]
    #array_of_dot_rois = [roi_dot2, roi_dot3, roi_dot4]
    # digit rois: (roi_top, roi_tr, roi_br, roi_bott, roi_bl, roi_tl, roi_midd)

    # MODE_INDICATORS = ["watt", "curr", "volt",  "freq", "ct", "ec", "pf"]
    # SEGMENT_NAMES = ["a", "b", "c", "d", "e", "f", "g"]
    # DOT_NAMES = ["0.001", "0.01", "0.1"]
    # DIGIT_NAMES = ["1E4", "1E3", "1E2", "1E1", "1E0"]
    
    # DIGITS, DOTS, MODES

    #At this point the dictionary should be updated for the entire LCD state. 
 
    digit_values = [
        decode_digit(lcd_state["digits"][name])
        for name in DIGIT_NAMES
    ]
    
    digit_1E4, digit_1E3, digit_1E2, digit_1E1, digit_1E0 = digit_values
    
    if any(v is None for v in digit_values):
        print("Warning: one or more segments failed to decode:", digit_values)
    else:
        # 4) Compute the total numeric value
        total_value = (
            digit_1E4 * 10_000 +
            digit_1E3 * 1_000 +
            digit_1E2 * 100 +
            digit_1E1 * 10 +
            digit_1E0
        ) * (
            0.001*lcd_state["dots"]["0.001"] +
            0.01*lcd_state["dots"]["0.01"] +
            0.1*lcd_state["dots"]["0.1"]
            )
        print(f"Decoded value: {total_value}")

    # Display
    cv2.imshow(window_name, frame_annotated_color)

    # Handle key & exit condition
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        return False

    # TODO: insert more processing here, e.g. detect/display ROIs, decode digits, etc.

    return True



def main():
    try:
        # -- initialize once --
        setup(resolution=(800, 600), framerate=30)

        # -- then run loop until it returns False --
        while loop():
            pass

    finally:
        # -- cleanup when done or on error --
        picam2.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
