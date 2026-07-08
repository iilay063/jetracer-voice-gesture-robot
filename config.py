"""
Central configuration for the GestureRacer project.

All tunable values live here so the rest of the code is free of magic
numbers. Adjust thresholds, control gains and detection parameters here
when calibrating on real hardware.
"""

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
# 224x224 keeps MediaPipe fast on the Nano's Maxwell GPU. Raise if
# classification accuracy suffers at the cost of FPS.
CAMERA_WIDTH = 224
CAMERA_HEIGHT = 224
CAMERA_FPS = 30

# ---------------------------------------------------------------------------
# Hand tracker (MediaPipe Hands)
# ---------------------------------------------------------------------------
# Single hand is enough for this project and roughly halves inference time.
HAND_MAX_HANDS = 1
HAND_DETECTION_CONFIDENCE = 0.6
HAND_TRACKING_CONFIDENCE = 0.5

# ---------------------------------------------------------------------------
# Gesture classifier
# ---------------------------------------------------------------------------
# A finger counts as "extended" when its segments (MCP->PIP and PIP->tip)
# are roughly collinear. We measure this with cosine similarity; a value
# of 1.0 is perfectly straight, 0.0 is bent at 90 degrees. 0.6 corresponds
# to roughly 53 degrees of allowed bend - permissive enough that "extended"
# fingers aren't required to be perfectly straight, strict enough that
# curled fingers don't sneak through.
# Rotation-invariant: works regardless of hand orientation in the frame.
FINGER_STRAIGHTNESS_COS_MIN = 0.6

# ---------------------------------------------------------------------------
# Robot control
# ---------------------------------------------------------------------------
# Hardware direction calibration. On our JetRacer the steering servo is
# wired so that positive steering values turn the WRONG way, so its sign
# is flipped here; the ESC/throttle direction is correct as-is. Signs are
# applied once, at the moment values are written to the hardware - all
# control logic works in the "natural" convention (positive throttle =
# forward, positive steering = right). Verified on the car 2026-07-08.
STEERING_SIGN = -1
THROTTLE_SIGN = 1

# Safety cap during development. Do not raise without supervision.
MAX_THROTTLE = 0.3

# Throttle for driving forward (voice "forward", closed-fist gesture).
FORWARD_THROTTLE = 0.25

# Throttle for reversing. Negative = reverse.
REVERSE_THROTTLE = -0.18

# Throttle while spinning in place.
SPIN_THROTTLE = 0.18

# Spin direction: +1 = clockwise (steer right), -1 = counter-clockwise.
# Up for review with the lecturer; flipped here means flipped everywhere.
SPIN_DIRECTION = 1

# Steering gain for the closed-loop "follow the hand" controller.
# Higher = sharper turns for the same horizontal hand offset.
STEERING_GAIN = 1.5

# Hand bounding-box width thresholds (fraction of frame width) used to
# scale forward throttle: hand close => stop, hand far => full forward.
HAND_SIZE_STOP = 0.5
HAND_SIZE_FAR = 0.15

# ---------------------------------------------------------------------------
# Voice control (Vosk, offline)
# ---------------------------------------------------------------------------
# Path to the unzipped Vosk model directory. Small English model is
# enough for our fixed 7-word vocabulary.
VOICE_MODEL_PATH = "vosk-model-small-en-us-0.15"

# Vosk models are trained at 16 kHz. Don't change unless using a model
# trained at a different rate.
VOICE_SAMPLE_RATE = 16000

# Audio input device index passed to sounddevice. None = OS default.
# Run `python3 voice_listener.py --list-devices` to list available indexes.
# Override at runtime with the --mic-device CLI flag.
VOICE_MIC_DEVICE_INDEX = None

# A motion command (forward, backward, turn, spin) drives the robot for
# at most this long, then the robot actively stops. Repeating the command
# (or saying a new one) resets the timer. This bounds how far the robot
# can travel if a "stop" is missed - deliberately short for safety.
VOICE_COMMAND_TIMEOUT_SEC = 5.0

# The full vocabulary. Order doesn't matter; Vosk uses this as a
# constrained grammar. "[unk]" lets non-matching speech be ignored
# instead of being force-matched to one of the commands.
#
# Word choice matters: with a constrained grammar Vosk force-matches
# speech to the *nearest* phrase, so entries must be phonetically far
# apart. That is why follow mode is "come" (not "follow", which collides
# with "forward") and turning is "turn right" (two syllables are much
# harder to false-trigger than a bare "right" spoken mid-sentence).
VOICE_COMMANDS = (
    "forward",
    "backward",
    "spin right",
    "spin left",
    "turn right",
    "turn left",
    "stop",
    "come",
)

# Fast path for "stop": act on Vosk's partial (mid-utterance) results
# instead of waiting for end-of-utterance silence. Cuts stop latency
# roughly in half. Disable if background conversation triggers too many
# false stops during a demo.
VOICE_FAST_STOP = True

# Minimum per-word confidence (0..1) for a recognized phrase to be
# accepted as a real command. Constrained-grammar recognizers always
# force-match to the nearest entry - e.g. "light" gets heard as "right"
# - but those forced matches usually come with lower confidence.
# Raise toward 1.0 if false positives still slip through; lower if real
# commands are being rejected.
VOICE_MIN_CONFIDENCE = 0.8

# Steering value used for the voice "turn right" / "turn left"
# commands. 0.5 is half-lock; raise toward 1.0 for tighter turns.
VOICE_TURN_STEERING = 0.5

# Audio block length fed to the recognizer, in seconds. Smaller blocks
# mean lower command latency (especially for "stop") at slightly higher
# callback overhead. 0.25 s is a good balance on the Nano.
VOICE_BLOCK_SEC = 0.25

# Maximum audio blocks buffered between the mic callback and the
# recognizer thread. If Vosk falls behind real time (e.g. CPU contention
# with MediaPipe), the OLDEST audio is dropped so recognition stays
# current - a laggy "stop" is worse than a missed word.
VOICE_QUEUE_MAX_BLOCKS = 16

# Mic watchdog: if no audio arrives from the input stream for this long
# while listening, the mic is considered dead (e.g. K9 wireless receiver
# unplugged or link dropped) and the robot is stopped.
VOICE_WATCHDOG_SEC = 2.0

# How long the "come" voice command keeps hand-following mode active.
# After this many seconds the robot stops and returns to waiting for
# voice commands. Saying "come" again resets the timer.
FOLLOW_TIMEOUT_SEC = 10.0

# ---------------------------------------------------------------------------
# Safety stop
# ---------------------------------------------------------------------------
# Cut motors after this long without any control input actively driving
# them (no live voice command, no hand while following). This is the
# last line of defense on top of the per-command timeouts.
SAFETY_STOP_SEC = 3.0

# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------
PRINT_DIAGNOSTICS = True
SHOW_DEBUG_WINDOW = False  # requires a display attached to the Jetson
