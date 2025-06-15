#!/usr/bin/env python3

from picamera2 import Picamera2
import cv2
import time

def capture_image(resolution=(640, 480), warmup=2.0):
    """
    Capture a single image from the Pi Camera and return it
    as a NumPy array in BGR color order (suitable for OpenCV).
    """
    picam2 = Picamera2()
    config = picam2.create_still_configuration(main={"size": resolution})
    picam2.configure(config)
    picam2.start()
    time.sleep(warmup)            
    rgb = picam2.capture_array()  
    picam2.stop()
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

if __name__ == "__main__":
    # 1) Grab the image
    img = capture_image(resolution=(800, 600), warmup=1.5)

    # 2) Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 3) Apply Canny edge detection (tune thresholds as needed)
    edges = cv2.Canny(gray, threshold1=50, threshold2=150)

    # 4) Display both
    cv2.imshow("Original Capture", img)
    cv2.imshow("Edges", edges)
    cv2.waitKey(0)          # press any key to close
    cv2.destroyAllWindows()
