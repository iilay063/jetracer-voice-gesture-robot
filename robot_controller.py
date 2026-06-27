"""
Thin jetracer wrapper.

Maps gestures and a target image position to (throttle, steering).
All numeric limits live in config.py; this file just routes commands.
"""

from typing import Optional, Tuple

import config
from gesture_classifier import Gesture


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class RobotController:
    def __init__(self, use_motors: bool = True):
        self._use_motors = use_motors
        self._car = None
        if use_motors:
            # Lazy import keeps non-Jetson dev environments importable.
            from jetracer.nvidia_racecar import NvidiaRacecar
            self._car = NvidiaRacecar()
        self.stop()

    # ----------------------------------------------------------------- core

    def _set(self, throttle: float, steering: float) -> None:
        throttle = _clamp(throttle, -config.MAX_THROTTLE, config.MAX_THROTTLE)
        steering = _clamp(steering, -1.0, 1.0)
        if config.PRINT_DIAGNOSTICS:
            print(f"[motor] throttle={throttle:+.2f}  steering={steering:+.2f}")
        if self._use_motors and self._car is not None:
            self._car.throttle = throttle
            self._car.steering = steering

    def stop(self) -> None:
        self._set(0.0, 0.0)

    # ------------------------------------------------------------ behaviour

    def steer_toward(self,
                     position: Tuple[float, float],
                     throttle: Optional[float] = None,
                     hand_size: Optional[float] = None) -> None:
        """Closed-loop steering: pulls steering toward the target's x
        offset from frame centre. If hand_size is provided, throttle scales
        with it so the car slows as the hand gets closer."""
        x, _ = position
        # Map [0..1] to [-1..+1], then scale by gain.
        steering = (x - 0.5) * 2.0 * config.STEERING_GAIN

        if throttle is None:
            if hand_size is None:
                throttle = config.FORWARD_THROTTLE
            else:
                throttle = self._throttle_from_hand_size(hand_size)

        self._set(throttle, steering)

    def _throttle_from_hand_size(self, size: float) -> float:
        # Linear ramp between FAR (full forward) and STOP (zero). Keeps the
        # control law predictable - useful when explaining in the oral defense.
        if size >= config.HAND_SIZE_STOP:
            return 0.0
        if size <= config.HAND_SIZE_FAR:
            return config.FORWARD_THROTTLE
        span = config.HAND_SIZE_STOP - config.HAND_SIZE_FAR
        frac = (config.HAND_SIZE_STOP - size) / span
        return config.FORWARD_THROTTLE * frac

    def execute_voice(self, command: str) -> None:
        """Drive the robot according to a recognized voice command.
        Voice commands are open-loop: no camera feedback, just fixed
        throttle and steering values."""
        if command == "forward":
            self._set(config.FORWARD_THROTTLE, 0.0)
        elif command == "backward":
            self._set(config.REVERSE_THROTTLE, 0.0)
        elif command == "spin right":
            self._set(config.SPIN_THROTTLE, 1.0)
        elif command == "spin left":
            self._set(config.SPIN_THROTTLE, -1.0)
        elif command == "right":
            self._set(config.FORWARD_THROTTLE, config.VOICE_TURN_STEERING)
        elif command == "left":
            self._set(config.FORWARD_THROTTLE, -config.VOICE_TURN_STEERING)
        elif command == "stop":
            self.stop()
        # "follow" is a mode switch, not a direct motor command; it is
        # handled entirely in main.py and never reaches this method.
        # Unknown voice command: leave motors in their current state
        # rather than risk an unsafe default.

    def execute(self,
                gesture: Gesture,
                target_position: Tuple[float, float],
                hand_size: float) -> None:
        if gesture == Gesture.OPEN_PALM:
            self.stop()
        elif gesture == Gesture.FIST:
            # Forward at fixed throttle while still steering toward the
            # hand, so the robot follows the user as they walk.
            self.steer_toward(target_position, throttle=config.FORWARD_THROTTLE)
        elif gesture == Gesture.PEACE:
            self.steer_toward(target_position, throttle=config.REVERSE_THROTTLE)
        elif gesture == Gesture.THUMBS_UP:
            # Spin in place: full-lock steering, modest throttle. Sign
            # controlled by config so it can be flipped without touching
            # this file.
            self._set(config.SPIN_THROTTLE, float(config.SPIN_DIRECTION))
        elif gesture == Gesture.POINT:
            # "Follow the fingertip" - main.py passes the fingertip as
            # target_position, so the same closed-loop control applies.
            self.steer_toward(target_position, hand_size=hand_size)
        else:
            # UNKNOWN: default tracking - steer toward hand, throttle by size.
            self.steer_toward(target_position, hand_size=hand_size)
