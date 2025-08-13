

# sudo apt update
# sudo apt install pigpio python3-pigpio        # if you haven’t already
# sudo systemctl'?/;'
enable pigpiod
# sudo systemctl start pigpiod

from gpiozero import AngularServo
import time

# No PiGPIOFactory → gpiozero will use software PWM
servo = AngularServo(
    12,              # BCM 12 (physical pin 32)
    min_pulse_width=0.0005,
    max_pulse_width=0.0025,
    frame_width=0.02
)

try:
    while True:
        servo.angle = 45
        time.sleep(0.2)
        servo.angle = -45
        time.sleep(1)
except KeyboardInterrupt:
    servo.detach()
