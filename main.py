"""
GestureRacer entry point.

Pipeline:
    frame -> hand_tracker -> gesture
    mic   -> voice_listener -> command
    arbiter -> robot_controller

Voice commands latch for config.VOICE_LATCH_SEC. During the latch
window the spoken command drives the robot and gestures are ignored.
After the window expires, gestures take over again if a hand is visible.
Stops on extended absence of any signal, or on any unhandled exception.
"""

import argparse
import faulthandler
import time

# Dump a Python traceback to stderr on segfault instead of dying silently.
faulthandler.enable()

import config
from camera import Camera
from gesture_classifier import Gesture, classify
from hand_tracker import HandTracker
from robot_controller import RobotController


def main() -> None:
    parser = argparse.ArgumentParser(description="Hand- and voice-controlled JetRacer.")
    parser.add_argument("--no-motors", action="store_true",
                        help="Run vision/voice pipeline only; do not drive motors.")
    parser.add_argument("--no-voice", action="store_true",
                        help="Disable the voice channel (gesture only).")
    parser.add_argument("--debug", action="store_true",
                        help="Show OpenCV debug window and print voice match confidences.")
    parser.add_argument("--mic-device", type=int, default=None,
                        help="Audio input device index. See --list-mics for options.")
    parser.add_argument("--list-mics", action="store_true",
                        help="Print available audio input devices and exit.")
    args = parser.parse_args()

    if args.list_mics:
        from voice_listener import list_devices
        list_devices()
        return

    camera = Camera()
    tracker = HandTracker()
    robot = RobotController(use_motors=not args.no_motors)

    # Voice is optional - if model/mic isn't available we degrade to
    # gesture-only rather than refusing to start.
    voice = None
    if not args.no_voice:
        try:
            from voice_listener import VoiceListener
            mic = args.mic_device if args.mic_device is not None else config.VOICE_MIC_DEVICE_INDEX
            voice = VoiceListener(verbose=args.debug, device_index=mic)
            voice.start()
            print("[voice] listening")
        except Exception as exc:
            print(f"[voice] disabled: {exc!r}")
            voice = None

    last_any_seen = time.time()
    last_frame_time = time.time()
    # Tracks which voice command was last acted upon, so we only log
    # mode transitions instead of every frame.
    last_acted_voice_time = 0.0
    # "follow" mode: voice-initiated free-tracking. Active until a new
    # voice command cancels it or FOLLOW_TIMEOUT_SEC elapses.
    follow_active = False
    follow_start = 0.0

    overlay = None
    if args.debug or config.SHOW_DEBUG_WINDOW:
        from utils.visualization import DebugOverlay
        overlay = DebugOverlay()

    try:
        while True:
            frame = camera.read()
            if frame is None:
                time.sleep(0.01)
                continue

            now = time.time()
            fps = 1.0 / max(now - last_frame_time, 1e-6)
            last_frame_time = now

            # Voice latch: a recent voice command takes priority over
            # whatever the camera sees, so a steady hand pose doesn't
            # immediately override the spoken command.
            voice_cmd, voice_cmd_time = (None, 0.0)
            if voice is not None:
                voice_cmd, voice_cmd_time = voice.latest()
            voice_active = (voice_cmd is not None
                            and (now - voice_cmd_time) < config.VOICE_LATCH_SEC)
            # True only on the first frame after a new command is heard.
            new_voice = (voice_cmd is not None
                         and voice_cmd_time != last_acted_voice_time)

            # --- Follow mode entry / exit ---
            # A new voice command transitions state regardless of latch.
            if new_voice:
                last_any_seen = now          # voice presence resets safety timer
                last_acted_voice_time = voice_cmd_time
                if voice_cmd == "follow":
                    follow_active = True
                    follow_start = now
                    print("[voice] -> 'follow' (free-tracking mode)")
                else:
                    if follow_active:
                        print("[voice] follow mode ended by command")
                    follow_active = False

            # Follow timeout: whichever fires first (new command above or
            # this timeout) ends follow mode.
            if follow_active and (now - follow_start) >= config.FOLLOW_TIMEOUT_SEC:
                print("[voice] follow timeout -> stop")
                follow_active = False
                robot.stop()

            hand = tracker.detect(frame)
            gesture = Gesture.UNKNOWN

            if follow_active:
                # Free-tracking: steer toward the hand exactly like POINT/
                # UNKNOWN, but voice-initiated. Only update safety timer when
                # a hand is visible; no hand => safety stop will fire normally.
                if hand is not None:
                    last_any_seen = now
                    robot.steer_toward(hand.center, hand_size=hand.size)
            elif voice_active and voice_cmd != "follow":
                # Normal latched voice command (forward, stop, spin …).
                last_any_seen = now
                robot.execute_voice(voice_cmd)
            elif hand is not None:
                last_any_seen = now
                gesture = classify(hand)
                # POINT mode follows the fingertip directly (landmark 8);
                # every other gesture follows the palm centre.
                target = hand.landmarks[8] if gesture == Gesture.POINT else hand.center
                robot.execute(gesture, target, hand.size)

            # Highest-priority safety rule: no detection for too long => stop.
            if now - last_any_seen >= config.SAFETY_STOP_SEC:
                robot.stop()

            if config.PRINT_DIAGNOSTICS:
                if follow_active:
                    mode = "follow "
                elif voice_active:
                    mode = "voice  "
                else:
                    mode = "gesture"
                print(f"[loop] fps={fps:5.1f}  mode={mode}"
                      f"  gesture={gesture.value}"
                      f"  hand={'yes' if hand else 'no '}")

            if overlay is not None:
                overlay.draw(frame, hand=hand, gesture=gesture, fps=fps)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as exc:
        # Safety: any unhandled exception must not leave the motors running.
        print(f"[fatal] {exc!r}")
        raise
    finally:
        robot.stop()
        tracker.close()
        camera.release()
        if voice is not None:
            voice.stop()
        if overlay is not None:
            overlay.close()


if __name__ == "__main__":
    main()
