"""
Optional OpenCV debug overlay.

Draws hand landmarks, the gesture label and FPS on a window. Only useful
when a display is attached to the Jetson, so importing is lazy.
"""

from typing import Optional

import numpy as np

from gesture_classifier import Gesture
from hand_tracker import Hand


class DebugOverlay:
    WINDOW = "JetRacer - Voice and Gesture Controlled Robot"

    def __init__(self) -> None:
        import cv2
        self._cv2 = cv2
        cv2.namedWindow(self.WINDOW, cv2.WINDOW_NORMAL)

    def draw(self,
             frame: np.ndarray,
             hand: Optional[Hand],
             gesture: Gesture,
             fps: float) -> None:
        cv2 = self._cv2
        canvas = frame.copy()
        h, w = canvas.shape[:2]

        if hand is not None:
            for (x, y) in hand.landmarks:
                cv2.circle(canvas, (int(x * w), int(y * h)), 2, (0, 255, 0), -1)
            cx, cy = hand.center
            cv2.circle(canvas, (int(cx * w), int(cy * h)), 5, (0, 255, 255), 2)

        cv2.putText(canvas, f"{gesture.value}  fps={fps:.1f}",
                    (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow(self.WINDOW, canvas)
        # 1 ms pumps the window event loop without throttling FPS.
        cv2.waitKey(1)

    def close(self) -> None:
        self._cv2.destroyAllWindows()
