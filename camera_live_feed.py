#!/usr/bin/env python3

import cv2
from picamera2 import Picamera2
import time

def live_preview(resolution=(640, 480), framerate=15):
    """
    Stream the camera feed live in an OpenCV window.
    
    :param resolution: tuple (width, height)
    :param framerate: frames per second
    """
    picam2 = Picamera2()
    # set up preview configuration at desired resolution/framerate
    config = picam2.create_preview_configuration(
        main={"size": resolution},
        lores={"size": resolution},  # optional lower-res stream if needed
        display="main"
    )
    picam2.configure(config)
    picam2.start()
    # tiny sleep so we don’t grab totally dark frames
    time.sleep(0.1)

    try:
        while True:
            # capture a frame as RGB array
            rgb = picam2.capture_array()
            # convert to BGR for OpenCV
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            cv2.imshow("PiCam Live Preview (press 'q' to quit)", bgr)

            # waitKey(1) for realtime; break if 'q' pressed
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    finally:
        picam2.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # tweak these as desired
    live_preview(resolution=(800, 600), framerate=30)
