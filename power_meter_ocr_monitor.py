#!/usr/bin/env python3

import cv2
import time
from picamera2 import Picamera2
from datetime import datetime

# Global handles (so both setup() and loop() can see them)
picam2 = None
window_name = "PiCam Live Preview (press 'q' to quit)"

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
    
    frame_annotated = frame_clean_gr.copy()
    
    # Annotate frame with date
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    
    # args: image, text, org (x,y), font, fontScale, color (BGR), thickness, lineType
    cv2.putText(
        frame_annotated,
        timestamp,
        (10, 30),                             # position in pixels from top-left
        cv2.FONT_HERSHEY_SIMPLEX,             # font face
        0.6,                                  # font scale (size)
        (255, 255, 255),                      # font color (white)
        2,                                    # thickness
        cv2.LINE_AA                           # anti-aliased line
    )

    # Display
    cv2.imshow(window_name, frame_annotated)

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
