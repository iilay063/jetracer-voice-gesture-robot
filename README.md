# GestureRacer

Voice-controlled robot car with hand-following. Final project for **Software Development for Human & Robot Humanoid Interaction** (HIT, Computer Science).

**Voice is the primary control channel.** The robot's camera points at the floor while driving, so it usually cannot see the user — spoken commands drive it. The camera is used for follow-the-hand mode (say `come`, put your hand on the floor in front of the robot), and full gesture control is available as an opt-in mode for elevated-surface demos where the camera can see the user.

## Hardware

- NVIDIA Jetson Nano (128-core Maxwell GPU)
- Waveshare JetRacer Pro AI Kit (Ackermann steering: front servo, rear drive)
- Raspberry Pi Camera v2 over CSI
- K9 wireless microphone (USB receiver — standard Linux audio input)

## How it works

```
mic    -> voice_listener -> command --------------> |
                                                    +-> robot_controller
frame  -> hand_tracker -> gesture_classifier ----> |   (follow / gesture mode only)
```

The main loop is a small state machine:

| State     | What drives the robot | How it ends |
|-----------|----------------------|-------------|
| `idle`    | Nothing — motors stopped | A voice command arrives |
| `command` | The current base motion (`forward`, `backward`, `spin …`) plus an optional turn | A new command, or auto-stop after `VOICE_COMMAND_TIMEOUT_SEC` (10 s) |
| `follow`  | Hand position in frame (closed-loop) | Any voice command, an open palm, or `FOLLOW_TIMEOUT_SEC` (10 s) |

`turn left` / `turn right` are **modifiers, not separate motions**: while driving forward or backward they just steer the wheels — the motion continues seamlessly. From a standstill they start a forward curve. Saying `forward`/`backward` again straightens the wheels. Every command (including turns) resets the timeout; after `VOICE_COMMAND_TIMEOUT_SEC` with nothing new the robot performs an **active stop** — a missed `stop` can never leave it driving away.

## Voice command vocabulary

| Say               | Command                                      |
|-------------------|----------------------------------------------|
| `stop`            | Stop motors immediately                      |
| `forward`         | Drive forward at fixed throttle              |
| `backward`        | Reverse at fixed throttle                    |
| `turn right`      | Steer right (keeps current motion; forward if idle) |
| `turn left`       | Steer left (keeps current motion; forward if idle)  |
| `spin right`      | Rotate in place clockwise                    |
| `spin left`       | Rotate in place counter-clockwise            |
| `come`            | Enter follow-the-hand mode (see below)       |

Recognition is offline (Vosk) — no internet or API key required on the Jetson. The grammar is constrained to exactly these phrases, and word choice is deliberate: entries are kept phonetically far apart (`come` instead of `follow`, which collides with `forward`; `turn right` instead of a bare `right`, which false-triggers in normal speech).

`stop` additionally has a **fast path**: it is recognized from Vosk's partial results mid-utterance, without waiting for end-of-utterance silence, so it acts noticeably faster than the other commands.

### Follow mode

Saying `come` switches the robot into hand-following: it steers toward the hand (toward the fingertip if you point) and scales throttle with hand distance. It exits on whichever comes first:

- **Any voice command** — e.g. `stop`.
- **Open palm** — a visual emergency stop that works even if the mic can't hear you over motor noise.
- **Timeout** — after `FOLLOW_TIMEOUT_SEC` seconds (default 10) the robot stops. Say `come` again to continue.

### Gesture mode (`--gesture-mode`)

For demos on an elevated surface where the camera faces the user, `--gesture-mode` enables the full gesture vocabulary whenever no voice command is active:

| Gesture           | Command                                      |
|-------------------|----------------------------------------------|
| Open palm         | Stop                                         |
| Closed fist       | Drive forward (steers toward hand)           |
| Thumbs up         | Spin in place                                |
| Peace sign        | Reverse                                      |
| Index finger only | Follow the fingertip                         |
| (no clear gesture)| Follow hand; throttle scales with distance   |

Without this flag a visible hand does **not** drive the robot (except in follow mode) — important because the floor-facing camera can catch your hand while you place or pick up the robot.

## Reliability of the voice channel

Because voice is the only way to command (and stop) the robot in normal operation, `voice_listener.py` is defensive:

- **Any mic format works.** Vosk needs 16 kHz mono; USB wireless receivers often only do 44.1/48 kHz stereo. The listener opens the mic at whatever format it supports and downmixes/resamples in software.
- **Mic watchdog.** If the wireless receiver drops mid-run, the robot stops immediately and waits for audio to return (`VOICE_WATCHDOG_SEC`).
- **Bounded audio queue.** If recognition falls behind real time, the oldest audio is dropped so a `stop` spoken *now* is never queued behind stale audio.
- **Fail loud.** If the mic can't be opened at startup, the program refuses to run (instead of silently degrading), unless you explicitly pass `--no-voice`.

## Setup

### Developing on a laptop (no Jetson needed)

The whole pipeline runs on a normal Linux laptop: `camera.py` falls back to the built-in webcam, the mic is whatever the OS default input is, and `--no-motors` skips the jetracer import entirely. This is the primary dev workflow — get everything working here first, then deploy to the Jetson.

```bash
# from the project root, using the project venv:
.venv/bin/python main.py --no-motors --debug
.venv/bin/python voice_listener.py          # voice-only smoke test
```

### Gesture / vision dependencies

The Jetson should already have OpenCV, `jetracer`, and `jetcam` from the JetRacer SD image. Install MediaPipe separately:

```bash
pip3 install mediapipe opencv-python
```

### Voice dependencies

Install on both laptop (dev) and Jetson:

```bash
pip3 install vosk sounddevice
```

Download the Vosk small English model (~40 MB) from https://alphacephei.com/vosk/models — look for `vosk-model-small-en-us-0.15`. Unzip it into the project root so the directory layout is:

```
GestureRacer/
└── vosk-model-small-en-us-0.15/
    ├── am/
    ├── conf/
    ├── graph/
    └── ...
```

> **Note:** the model folder is excluded from git (`.gitignore`). Every developer and the Jetson must download it separately.

### Selecting a microphone

By default the OS audio input device is used. To select a specific mic:

```bash
# List available input devices and their index numbers:
python3 main.py --list-mics

# Run with a specific device:
python3 main.py --mic-device 2

# Or set permanently in config.py:
VOICE_MIC_DEVICE_INDEX = 2
```

The standalone voice smoke test also accepts these flags:

```bash
python3 voice_listener.py --list-devices
python3 voice_listener.py --device 2
```

### Jetson Nano gotchas (both hit us in practice)

1. **`Illegal instruction (core dumped)` on `import numpy`** — OpenBLAS misdetects the Nano's Cortex-A57. Fix once:

   ```bash
   echo 'export OPENBLAS_CORETYPE=ARMV8' >> ~/.bashrc
   source ~/.bashrc
   ```

2. **`Segmentation fault (core dumped)` on `import vosk`** — every vosk version on PyPI for Python 3.6/aarch64 (0.3.43-0.3.45) crashes on the Nano. Install 0.3.32 from vosk's GitHub releases instead (verified working on JetPack 4.5.1):

   ```bash
   python3 -m pip install https://github.com/alphacep/vosk-api/releases/download/v0.3.32/vosk-0.3.32-py3-none-linux_aarch64.whl
   ```

   (The `urllib3 or chardet doesn't match a supported version` warning that prints alongside is harmless — it comes from `requests` on every JetPack image.)

## Run

```bash
# Safe to run on a desk - vision + voice pipeline, motors disabled.
python3 main.py --no-motors --debug

# Full system, voice-first (floor). Test on an open floor.
python3 main.py

# Elevated-surface demo: gestures drive when no voice command is active.
python3 main.py --gesture-mode

# Gesture only (no mic required; implies --gesture-mode).
python3 main.py --no-voice

# Camera smoke test.
python3 camera.py

# Voice smoke test (laptop or Jetson, no camera needed).
python3 voice_listener.py
```

All tunable values live in `config.py`. Calibrate there first, not in code.

## Project layout

| File | Role |
|------|------|
| `main.py` | Entry point: voice-first state machine (idle / command / follow) |
| `config.py` | All thresholds, gains and timeouts |
| `camera.py` | CSI camera via GStreamer pipeline (USB webcam fallback for dev PCs) |
| `hand_tracker.py` | MediaPipe Hands — returns 21 landmarks |
| `gesture_classifier.py` | Rule-based landmarks → gesture |
| `voice_listener.py` | Offline Vosk recognition + mic resilience (resample, watchdog, fast stop) |
| `robot_controller.py` | jetracer wrapper — voice/gesture → motors |
| `utils/visualization.py` | Optional OpenCV debug overlay |

## Safety

- Throttle is hard-capped at `MAX_THROTTLE = 0.3` during development.
- Every motion command auto-stops after `VOICE_COMMAND_TIMEOUT_SEC` (5 s) — a missed `stop` is bounded.
- The mic watchdog stops the robot if the wireless receiver dies mid-run.
- A global safety stop fires after `SAFETY_STOP_SEC` (3 s) with nothing actively driving.
- Follow mode has its own `FOLLOW_TIMEOUT_SEC` timeout on top of the safety stop.
- The main loop's `finally` block always calls `robot.stop()`.
- Default to `--no-motors` until each new feature is hardware-tested.
- Always test on the floor. Never on a table.

## Course-topic mapping

| Component | Course topic |
|-----------|--------------|
| `camera.py` + OpenCV frame handling | Embedded computer vision |
| `hand_tracker.py` (MediaPipe on GPU) | Embedded deep learning |
| `gesture_classifier.py` | Gesture recognition |
| `robot_controller.steer_toward` (image position as feedback signal) | Closed-loop control |
| `robot_controller.py` (servo + motor coordination) | Mechatronics basics |
| `voice_listener.py` (Vosk on-device inference) | Embedded deep learning |

## Status

See `TODO.md` for open questions and tunables that still need on-hardware calibration.
