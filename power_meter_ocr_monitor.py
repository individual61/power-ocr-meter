#!/usr/bin/env python3

import cv2
import time
from picamera2 import Picamera2
from datetime import datetime

# Global handles (so both setup() and loop() can see them)
picam2 = None
window_name = "PiCam Live Preview (press 'q' to quit)"

roi_offs_x = 0
roi_offs_y = 0
roi_watt = (22, 196, 112, 232)
roi_curr = (22, 237, 93, 276)
roi_volt = (22, 280, 107, 317)
roi_freq = (22, 367, 111, 401)
roi_ct =   (112, 68, 178, 117)
roi_ec =   (418, 73, 485, 125)
roi_pf =   (151, 132, 210, 177)
digit_width = 115
digit_height = 200
dot_width = 24
dot_height = 24
roi_digit1 = (121, 200, 121 + digit_width, 207 + digit_height)
roi_digit2 = (236, 200, 236 + digit_width, 207 + digit_height)
roi_digit3 = (361, 200, 361 + digit_width, 207 + digit_height)
roi_digit4 = (491, 200, 491 + digit_width, 209 + digit_height)
roi_digit5 = (618, 200, 618 + digit_width, 210 + digit_height)
#roi_dot1 =   (221, 380, 221 + dot_width, 380 + dot_height)
roi_dot2 =   (341, 378, 341 + dot_width, 378 + dot_height)
roi_dot3 =   (464, 379, 464 + dot_width, 379 + dot_height)
roi_dot4 =   (592, 382, 592 + dot_width, 382 + dot_height)


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
    
    print(roi_watt)

frame_clean_gr_prev = None

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
    frame_clean_gr = cv2.cvtColor(frame_clean, cv2.COLOR_BGR2GRAY)
    
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
        (255, 255, 255),                      # font color (white)
        2,                                    # thickness
        cv2.LINE_AA                           # anti-aliased line
    )
    
    
    #### Annotate with ROI boxes
    x1, y1, x2, y2 = roi_watt
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 255, 0),
        1
        )
    
    x1, y1, x2, y2 = roi_curr
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 255, 0),
        1
        )
    
    x1, y1, x2, y2 = roi_volt
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 255, 0),
        1
        )
    
    x1, y1, x2, y2 = roi_freq
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 255, 0),
        1
        )
    
    x1, y1, x2, y2 = roi_ct
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 255, 0),
        1
        )
    
    x1, y1, x2, y2 = roi_ec
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 255, 0),
        1
        )
    
    x1, y1, x2, y2 = roi_pf
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 255, 0),
        1
        )
    
    x1, y1, x2, y2 = roi_digit1
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 0, 255),
        1
        )
    
    x1, y1, x2, y2 = roi_digit2
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 0, 255),
        1
        )
    
    x1, y1, x2, y2 = roi_digit3
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 0, 255),
        1
        )
    
    x1, y1, x2, y2 = roi_digit4
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 0, 255),
        1
        )
    
    x1, y1, x2, y2 = roi_digit5
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (0, 0, 255),
        1
        )
    
#     x1, y1, x2, y2 = roi_dot1
#     cv2.rectangle(
#         frame_annotated_color,
#         (x1 + roi_offs_x, y1 + roi_offs_y),
#         (x2 + roi_offs_x, y2 + roi_offs_y),
#         (255, 0, 0),
#         1
#         )
    
    x1, y1, x2, y2 = roi_dot2
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (255, 0, 0),
        1
        )
    
    x1, y1, x2, y2 = roi_dot3
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (255, 0, 0),
        1
        )
    
    x1, y1, x2, y2 = roi_dot4
    cv2.rectangle(
        frame_annotated_color,
        (x1 + roi_offs_x, y1 + roi_offs_y),
        (x2 + roi_offs_x, y2 + roi_offs_y),
        (255, 0, 0),
        1
        )

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
