# CLAUDE.md

Project-specific instructions for Claude Code. Read this fully before generating or modifying code in this repository.

---

## Project Overview

Academic project for the course **"Software Development for Human & Robot Humanoid Interaction"** at Holon Institute of Technology (HIT), Computer Science department.

**Goal:** Build a robot controlled primarily by **voice commands**, with hand-following as the secondary vision feature. Demonstrates Human-Robot Interaction (HRI) using embedded speech recognition and computer vision.

**Design pivot (July 2026):** the camera on the JetRacer points at the floor while driving, so it rarely sees the user's hands. Voice (offline Vosk) is therefore the primary control channel and **must be rock-solid**. Gestures are used for follow-the-hand on the floor (entered by voice), and full gesture control exists only as an opt-in mode (`--gesture-mode`) for elevated-surface demos.

**Stakes:** Final project = 70% of course grade. Includes oral defense in Hebrew with the lecturer (Eng. Idan Tobis).

---

## Hardware (Important - Do Not Assume)

- **Compute:** NVIDIA **Jetson Nano** (the syllabus mentions Raspberry Pi, but the actual lab provides Jetson - do NOT generate RPi-specific code)
- **Platform:** Waveshare **JetRacer Pro AI Kit** - 4-wheel car with Ackermann steering (1 drive motor rear, 1 steering servo front)
- **Camera:** CSI camera (Raspberry Pi Camera v2) connected via ribbon cable - points at the floor while driving
- **Microphone:** **K9 wireless mic** with USB receiver dongle (shows up as a standard Linux audio input; may only support 44.1/48 kHz - the voice listener resamples in software)
- **GPU:** 128-core Maxwell - use it for inference, not the CPU
- **No 3D printing.** The user does not want to design or print parts. Work with what exists.

---

## Tech Stack

- **Python 3.6+** (Jetson Nano default - some libs may not support newer Python)
- **OpenCV** (cv2) - bundled with JetPack
- **MediaPipe** - for hand detection and landmark extraction (21 landmarks per hand)
- **jetracer** - official NVIDIA library for the JetRacer platform
- **jetcam** - CSI camera access via GStreamer
- **NumPy**

Do NOT introduce: PyTorch training pipelines, ROS, heavy frameworks. Keep dependencies minimal.

---

## Project Features (Priority Order)

### MVP (must work — voice is the primary channel)
1. **Voice command vocabulary** (offline Vosk, constrained grammar):
   `forward`, `backward`, `turn right`, `turn left`, `spin right`, `spin left`, `stop`, `come`.
   Every motion command auto-stops after `VOICE_COMMAND_TIMEOUT_SEC`; `stop` has a fast path via Vosk partial results. Vocabulary words must stay phonetically far apart (this is why follow mode is `come`, not `follow`).
2. **Voice-channel reliability:** mic format fallback + resampling (wireless USB receivers are picky), mic-death watchdog, bounded audio queue, fail-loud startup.

### Core features
3. **Follow-the-hand mode:** entered by saying `come`. Robot steers toward the hand (fingertip when pointing) on the floor in front of it; throttle scales with hand size. Exits on any voice command, open palm, or timeout.

### Opt-in (elevated-surface demo only)
4. **Gesture command vocabulary** (`--gesture-mode` flag; map MediaPipe landmarks to commands):
   - Open palm (5 fingers extended) → STOP
   - Closed fist → forward
   - Thumbs up → spin 360°
   - Peace sign (2 fingers) → reverse
   - Index finger only → "follow the fingertip" mode

### Stretch goals
5. **OLED feedback:** Use the onboard OLED display to show current state (e.g., "IDLE", "FORWARD", "FOLLOW").

### Always on
6. **Safety stop:** per-command timeouts, mic watchdog, and a global stop after `SAFETY_STOP_SEC` with nothing actively driving, or if the pipeline crashes.

---

## Recommended Architecture

```
/project_root
├── main.py                  # Entry point: voice-first state machine
├── config.py                # All tunable parameters (no magic numbers in other files)
├── camera.py                # CSI camera via GStreamer (USB fallback on dev PCs)
├── hand_tracker.py          # MediaPipe hand detection
├── gesture_classifier.py    # Maps 21 landmarks → gesture name
├── voice_listener.py        # Offline Vosk recognition + mic resilience
├── robot_controller.py      # jetracer wrapper: steer, throttle, stop
└── utils/
    └── visualization.py     # Debug overlay (toggle via flag)
```

**Main loop shape** — a three-state machine, driven by voice:
```python
while running:
    frame = camera.read()
    cmd = voice.latest()          # + mic watchdog check
    # new command? -> transition: stop / follow ("come") / motion command
    if mode == COMMAND:           # motion cmd until new cmd or timeout, then STOP
        robot.execute_voice(active_cmd)
    elif mode == FOLLOW:          # "come": steer toward hand, open palm exits
        robot.steer_toward(hand)
    elif gesture_mode and hand:   # opt-in, elevated-surface demos only
        robot.execute(gesture, hand)
    # global safety stop if nothing drove the motors recently
```

Keep the main loop **synchronous and simple**. The only thread is the voice recognizer's (audio must be consumed continuously); everything else stays in the loop.

---

## Coding Guidelines

- **Clarity > cleverness.** Every line must be explainable in the oral defense. If a junior student couldn't read it, rewrite it.
- **Comment the WHY, not the WHAT.** Especially for thresholds, control gains, and gesture heuristics.
- **All tunable values live in `config.py`.** No magic numbers scattered in code.
- **Type hints** where they aid readability. Don't go overboard.
- **Print diagnostics** during dev: FPS, detected gesture, current motor values.
- **No premature optimization.** Get it working, then measure.
- **Filenames and identifiers in English.** Comments may be in English. UI/print messages can be in Hebrew if helpful for the demo.

---

## Critical Library Notes

### jetracer
```python
from jetracer.nvidia_racecar import NvidiaRacecar
car = NvidiaRacecar()
car.throttle = 0.2   # range -1.0 to 1.0
car.steering = 0.0   # range -1.0 to 1.0 (negative = left)
```
**Hard cap throttle at 0.3 during development.**

### jetcam (CSI camera)
Do NOT use `cv2.VideoCapture(0)` for the CSI camera - it's unreliable on Jetson. Use:
```python
from jetcam.csi_camera import CSICamera
camera = CSICamera(width=224, height=224, capture_fps=30)
```

### MediaPipe Hands - Landmark Reference
- Landmark 0 = wrist
- Landmark 4 = thumb tip
- Landmark 8 = index fingertip
- Landmark 12 = middle fingertip
- Landmark 16 = ring fingertip
- Landmark 20 = pinky tip
- For gesture classification: compare fingertip Y to PIP joint Y (landmarks 6, 10, 14, 18) to detect "extended" vs "curled" fingers.

---

## Commands

```bash
# Run the full system
python3 main.py

# Vision-only mode (no motors - safe for testing on a desk)
python3 main.py --no-motors

# Test camera feed
python3 camera.py

# One-time setup (mediapipe must match Jetson's Python version)
pip3 install mediapipe opencv-python
```

---

## Safety Rules (Non-Negotiable)

⚠️ This is a **moving robot with motors**. Always:

1. Wrap the main loop in `try/except` that calls `robot.stop()` on any exception.
2. Hard speed cap during development: `MAX_THROTTLE = 0.3` in config.
3. Default to `--no-motors` mode in any code that's not been hardware-tested yet.
4. Test on an open floor, never on a table.
5. The safety stop (no detection for 3 sec) is the highest-priority feature - never bypass it for a feature.

---

## Course Alignment (for the Defense)

The lecturer values projects that demonstrate course topics. Where relevant, frame code/comments around:

- **Embedded Computer Vision** (OpenCV on Jetson)
- **Embedded Deep Learning** (MediaPipe model running on Jetson's GPU)
- **Gesture recognition** (explicit course topic)
- **Open-loop vs closed-loop control** (the hand-following IS closed-loop control - vision is the feedback signal)
- **Mechatronics basics** (servo + motor coordination)

The README should briefly map each major component to a course topic.

---

## Behavioral Rules for Claude Code

1. **Always view existing files before editing.** Don't rewrite from memory.
2. **Ask before adding features.** This is a student project; feature creep kills deadlines. If the user asks for X, do X - don't also do Y "while we're at it."
3. **Ask before changing the architecture.** If a single-file solution is clearer for a small task, suggest it rather than forcing the multi-file layout.
4. **Never silently install packages.** Suggest the install command; let the user run it.
5. **Don't generate training code.** All models used here are pre-trained.
6. **When in doubt about hardware behavior, say so.** Don't guess at jetracer or jetcam API behavior - ask the user to test and report back.
7. **For ambiguity in gestures or control mappings, ask first.** Examples: "Should 'thumbs up' rotate clockwise or counterclockwise?" "What FPS target are we aiming for?"

---

## Open Questions to Resolve With the User

Track these in `TODO.md` until answered:

- [ ] Has the CSI camera been verified working on this specific Jetson?
- [ ] Is the `jetracer` library already installed and tested?
- [ ] What's the target demo environment - hallway, lab floor, classroom?
- [ ] Required FPS for smooth tracking? (15? 30?)
- [ ] Are there specific gestures the lecturer wants to see, or is the vocabulary up to the student?
- [ ] Is the OLED display feature in scope, or stretch goal only?
