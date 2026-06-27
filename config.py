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
# Safety cap during development. Do not raise without supervision.
MAX_THROTTLE = 0.3

# Throttle for the closed-fist "forward" gesture.
FORWARD_THROTTLE = 0.2

# Throttle for the peace-sign "reverse" gesture. Negative = reverse.
REVERSE_THROTTLE = -0.15

# Throttle while spinning in place for the thumbs-up gesture.
SPIN_THROTTLE = 0.15

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

# After hearing a voice command, ignore gesture input for this long so
# the spoken command actually takes effect instead of being immediately
# overridden by a steady hand pose. A new voice command resets the timer.
VOICE_LATCH_SEC = 3.0

# The full vocabulary. Order doesn't matter; Vosk uses this as a
# constrained grammar. "[unk]" lets non-matching speech be ignored
# instead of being force-matched to one of the commands.
VOICE_COMMANDS = (
    "forward",
    "backward",
    "spin right",
    "spin left",
    "right",
    "left",
    "stop",
    "follow",
)

# Minimum per-word confidence (0..1) for a recognized phrase to be
# accepted as a real command. Constrained-grammar recognizers always
# force-match to the nearest entry - e.g. "light" gets heard as "right"
# - but those forced matches usually come with lower confidence.
# Raise toward 1.0 if false positives still slip through; lower if real
# commands are being rejected.
VOICE_MIN_CONFIDENCE = 0.8

# Steering value used for the voice "right" and "left" turn-while-going
# commands. 0.5 is half-lock; raise toward 1.0 for tighter turns.
VOICE_TURN_STEERING = 0.5

# How long the "follow" voice command keeps free-tracking mode active.
# After this many seconds with no new voice command the robot stops and
# returns to normal command handling. Saying any command resets this.
FOLLOW_TIMEOUT_SEC = 10.0

# ---------------------------------------------------------------------------
# Safety stop
# ---------------------------------------------------------------------------
# Cut motors after this long with no detection of any kind.
SAFETY_STOP_SEC = 3.0

# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------
PRINT_DIAGNOSTICS = True
SHOW_DEBUG_WINDOW = False  # requires a display attached to the Jetson
