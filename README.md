# GestureRacer

Hand-gesture- and voice-controlled robot car. Final project for **Software Development for Human & Robot Humanoid Interaction** (HIT, Computer Science).

The robot uses its onboard camera to find the user's hand, steers toward it, and reacts to a small vocabulary of gestures and spoken commands.

## Hardware

- NVIDIA Jetson Nano (128-core Maxwell GPU)
- Waveshare JetRacer Pro AI Kit (Ackermann steering: front servo, rear drive)
- Raspberry Pi Camera v2 over CSI
- USB or wireless microphone (standard Linux audio input)

## How it works

```
frame  -> hand_tracker -> gesture_classifier -> |
                                                 +-> robot_controller
mic    -> voice_listener -> command -----------> |
```

The main loop runs synchronously at camera FPS. Voice commands latch for `VOICE_LATCH_SEC` (3 s); during that window gestures are ignored so the spoken command takes effect. After the latch expires, gesture control resumes automatically. If nothing is detected for 3 s the safety stop cuts the motors.

## Gesture vocabulary

| Gesture           | Command                                      |
|-------------------|----------------------------------------------|
| Open palm         | Stop                                         |
| Closed fist       | Drive forward (steers toward hand)           |
| Thumbs up         | Spin in place                                |
| Peace sign        | Reverse                                      |
| Index finger only | Follow the fingertip                         |
| (no clear gesture)| Follow hand; throttle scales with distance   |

## Voice command vocabulary

| Say               | Command                                      |
|-------------------|----------------------------------------------|
| `stop`            | Stop motors immediately                      |
| `forward`         | Drive forward at fixed throttle              |
| `backward`        | Reverse at fixed throttle                    |
| `right`           | Drive forward, turn right                    |
| `left`            | Drive forward, turn left                     |
| `spin right`      | Rotate in place clockwise                    |
| `spin left`       | Rotate in place counter-clockwise            |
| `follow`          | Enter free-tracking mode (see below)         |

### Follow mode

Saying `follow` switches the robot into free-tracking mode: it steers toward the hand and scales throttle with distance, identical to the gesture-UNKNOWN/POINT path. This mode exits under two conditions — whichever comes first:

- **Voice stop:** saying any other command (e.g. `stop`) ends follow mode immediately.
- **Timeout:** follow mode ends automatically after `FOLLOW_TIMEOUT_SEC` seconds (default 10). The robot stops and returns to normal command handling.

Recognition is offline (Vosk) — no internet or API key required on the Jetson.

## Setup

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

## Run

```bash
# Safe to run on a desk - vision + voice pipeline, motors disabled.
python3 main.py --no-motors --debug

# Gesture only (no mic required).
python3 main.py --no-voice

# Full system. Test on an open floor.
python3 main.py

# Camera smoke test.
python3 camera.py

# Voice smoke test (laptop or Jetson, no camera needed).
python3 voice_listener.py
```

All tunable values live in `config.py`. Calibrate there first, not in code.

## Project layout

| File | Role |
|------|------|
| `main.py` | Entry point and main loop |
| `config.py` | All thresholds, gains and timeouts |
| `camera.py` | CSI camera wrapper via jetcam |
| `hand_tracker.py` | MediaPipe Hands — returns 21 landmarks |
| `gesture_classifier.py` | Rule-based landmarks → gesture |
| `voice_listener.py` | Offline Vosk speech recognition; `list_devices()` helper |
| `robot_controller.py` | jetracer wrapper — gesture/voice → motors |
| `utils/visualization.py` | Optional OpenCV debug overlay |

## Safety

- Throttle is hard-capped at `MAX_THROTTLE = 0.3` during development.
- The main loop's `finally` block always calls `robot.stop()`.
- Safety stop kicks in after 3 s of no detection of any kind (hand or voice).
- Follow mode has its own `FOLLOW_TIMEOUT_SEC` timeout on top of the safety stop.
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
