"""
GestureRacer entry point - voice-first control.

Pipeline:
    mic   -> voice_listener -> command  (PRIMARY channel)
    frame -> hand_tracker   -> target   (only in follow / gesture mode)

State machine (MODE):
    idle    - motors stopped, waiting for a voice command.
    command - a motion command ("forward", "turn left", ...) is driving
              the robot. Ends on a new command or after
              VOICE_COMMAND_TIMEOUT_SEC, whichever comes first.
    follow  - entered by saying "come": the robot steers toward the
              hand (fingertip when pointing), throttle scales with hand
              distance. Ends on any voice command, an open palm, or
              after FOLLOW_TIMEOUT_SEC.

The camera points at the floor most of the time, so gestures are NOT a
default control channel - the vision branch only runs in follow mode.
For elevated-surface demos, --gesture-mode restores full gesture control
whenever no voice command is active.

Safety:
    - every motion command has a hard timeout, then an active stop;
    - a mic watchdog stops the robot if the wireless receiver dies;
    - a global safety stop fires if nothing has driven the motors for
      SAFETY_STOP_SEC;
    - any unhandled exception stops the motors on the way out.
"""

import argparse
import faulthandler
import time

# Dump a Python traceback to stderr on segfault instead of dying silently.
faulthandler.enable()

import config
from gesture_classifier import Gesture, classify
from robot_controller import RobotController

MODE_IDLE = "idle"
MODE_COMMAND = "command"
MODE_FOLLOW = "follow"


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice- and hand-controlled JetRacer.")
    parser.add_argument("--no-motors", action="store_true",
                        help="Run vision/voice pipeline only; do not drive motors.")
    parser.add_argument("--no-voice", action="store_true",
                        help="Disable the voice channel (gesture only; implies --gesture-mode).")
    parser.add_argument("--gesture-mode", action="store_true",
                        help="Enable full gesture control when no voice command is "
                             "active (for elevated-surface demos where the camera "
                             "can see the user).")
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

    # Without voice the only way to control the robot is gestures.
    gesture_mode = args.gesture_mode or args.no_voice

    # Voice is the primary channel: failing to start it is fatal unless
    # the user explicitly opted out with --no-voice.
    voice = None
    if not args.no_voice:
        from voice_listener import VoiceListener
        mic = args.mic_device if args.mic_device is not None else config.VOICE_MIC_DEVICE_INDEX
        try:
            voice = VoiceListener(verbose=args.debug, device_index=mic)
            voice.start()
        except Exception as exc:
            raise SystemExit(
                f"[voice] FAILED to start: {exc!r}\n"
                "Voice is the primary control channel. Check the mic with\n"
                "  python3 main.py --list-mics\n"
                "or run gesture-only with --no-voice.")
        print("[voice] listening")

    # The camera is only needed for follow / gesture mode. A broken
    # camera should not take down voice control, so degrade with a
    # warning instead of refusing to start.
    camera = None
    tracker = None
    try:
        from camera import Camera
        from hand_tracker import HandTracker
        camera = Camera()
        tracker = HandTracker()
    except Exception as exc:
        if gesture_mode:
            raise  # gestures without a camera cannot work at all
        print(f"[camera] unavailable ({exc!r}) - follow mode disabled, "
              "voice commands still work")

    robot = RobotController(use_motors=not args.no_motors)

    overlay = None
    if (args.debug or config.SHOW_DEBUG_WINDOW) and camera is not None:
        from utils.visualization import DebugOverlay
        overlay = DebugOverlay()

    mode = MODE_IDLE
    active_cmd = ""            # motion command currently driving (MODE_COMMAND)
    mode_start = 0.0           # when the current command/follow began
    last_cmd_time = 0.0        # timestamp of the last voice command acted on
    last_drive_time = time.time()  # last moment something actively drove motors
    last_frame_time = time.time()
    mic_alarm = False          # so the watchdog warning prints once, not every frame

    try:
        while True:
            frame = None
            if camera is not None:
                frame = camera.read()
            if frame is None:
                # Voice-only operation still needs the loop to spin.
                time.sleep(0.02)

            now = time.time()
            fps = 1.0 / max(now - last_frame_time, 1e-6)
            last_frame_time = now

            # --- Mic watchdog: a dead mic means no way to say "stop". ---
            # While alarmed, command processing below is skipped, so the
            # robot stays in idle until audio returns.
            if voice is not None:
                if not voice.is_healthy():
                    if not mic_alarm:
                        print("[voice] MIC LOST - stopping robot until audio returns")
                        mic_alarm = True
                        robot.stop()
                        mode = MODE_IDLE
                elif mic_alarm:
                    print("[voice] mic recovered")
                    mic_alarm = False

            # --- New voice command? ---
            voice_cmd = None
            if voice is not None and not mic_alarm:
                voice_cmd, voice_cmd_time = voice.latest()
                if voice_cmd is not None and voice_cmd_time != last_cmd_time:
                    last_cmd_time = voice_cmd_time
                    if voice_cmd == "stop":
                        print("[voice] 'stop'")
                        robot.stop()
                        mode = MODE_IDLE
                    elif voice_cmd == "come":
                        print("[voice] 'come' -> follow mode")
                        mode = MODE_FOLLOW
                        mode_start = now
                    else:
                        print(f"[voice] '{voice_cmd}'")
                        mode = MODE_COMMAND
                        active_cmd = voice_cmd
                        mode_start = now

            # --- Act on the current mode. ---
            hand = None
            gesture = Gesture.UNKNOWN

            if mode == MODE_COMMAND:
                if now - mode_start >= config.VOICE_COMMAND_TIMEOUT_SEC:
                    # Timed out with no follow-up command: active stop, so a
                    # missed "stop" can never leave the robot driving away.
                    print(f"[voice] '{active_cmd}' timed out -> stop")
                    robot.stop()
                    mode = MODE_IDLE
                else:
                    robot.execute_voice(active_cmd)
                    last_drive_time = now

            elif mode == MODE_FOLLOW:
                if now - mode_start >= config.FOLLOW_TIMEOUT_SEC:
                    print("[follow] timeout -> stop")
                    robot.stop()
                    mode = MODE_IDLE
                elif tracker is not None and frame is not None:
                    hand = tracker.detect(frame)
                    if hand is not None:
                        gesture = classify(hand)
                        if gesture == Gesture.OPEN_PALM:
                            # Open palm is an emergency stop that also works
                            # when the robot cannot hear over motor noise.
                            print("[follow] open palm -> stop")
                            robot.stop()
                            mode = MODE_IDLE
                        else:
                            # Steer toward the fingertip when pointing,
                            # otherwise the palm centre.
                            target = (hand.landmarks[8]
                                      if gesture == Gesture.POINT else hand.center)
                            robot.steer_toward(target, hand_size=hand.size)
                            last_drive_time = now
                    # No hand: motors keep their last value briefly; the
                    # global safety stop below cuts them if the hand stays
                    # lost for SAFETY_STOP_SEC.
                else:
                    print("[follow] no camera available -> stop")
                    robot.stop()
                    mode = MODE_IDLE

            elif gesture_mode and tracker is not None and frame is not None:
                # Elevated-surface demo: full gesture vocabulary drives the
                # robot whenever no voice command is active.
                hand = tracker.detect(frame)
                if hand is not None:
                    gesture = classify(hand)
                    target = (hand.landmarks[8]
                              if gesture == Gesture.POINT else hand.center)
                    robot.execute(gesture, target, hand.size)
                    last_drive_time = now

            # --- Global safety stop: nothing driving for too long. ---
            if now - last_drive_time >= config.SAFETY_STOP_SEC:
                robot.stop()
                last_drive_time = now  # avoid re-stopping every frame

            # Print only while something is driving; an idle robot would
            # otherwise flood the console at camera FPS.
            if config.PRINT_DIAGNOSTICS and (mode != MODE_IDLE or hand is not None):
                print(f"[loop] fps={fps:5.1f}  mode={mode:7s}"
                      f"  cmd={active_cmd if mode == MODE_COMMAND else '-':10s}"
                      f"  gesture={gesture.value}"
                      f"  hand={'yes' if hand else 'no '}")

            if overlay is not None and frame is not None:
                overlay.draw(frame, hand=hand, gesture=gesture, fps=fps)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as exc:
        # Safety: any unhandled exception must not leave the motors running.
        print(f"[fatal] {exc!r}")
        raise
    finally:
        robot.stop()
        if tracker is not None:
            tracker.close()
        if camera is not None:
            camera.release()
        if voice is not None:
            voice.stop()
        if overlay is not None:
            overlay.close()


if __name__ == "__main__":
    main()
