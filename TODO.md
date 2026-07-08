# Open Questions

Track these until answered (per CLAUDE.md).

## Voice (primary channel) - needs on-hardware validation

- [ ] Run `python3 voice_listener.py` on the Jetson with the K9 mic: confirm the receiver opens (watch for the "converting to 16000 Hz mono" line) and all 8 commands are recognized reliably.
- [ ] Tune `VOICE_MIN_CONFIDENCE` with `--debug` on the Jetson: with a constrained grammar the confidence may sit at 1.0 even for wrong matches - verify it actually discriminates.
- [ ] Is `VOICE_COMMAND_TIMEOUT_SEC = 5.0` right for the demo? (Long enough to cross the demo space, short enough to be safe.)
- [ ] Does a full 360° spin complete within the command timeout at `SPIN_THROTTLE = 0.15`?
- [ ] Test the mic watchdog for real: pull the K9 receiver mid-drive, robot must stop within ~2 s.
- [ ] Vosk recognition latency on the Nano's CPU while MediaPipe runs - if it lags, consider skipping hand detection except in follow mode (already done) or a smaller `VOICE_BLOCK_SEC`.

## From CLAUDE.md

- [ ] Has the CSI camera been verified working on this specific Jetson?
- [ ] Is the `jetracer` library already installed and tested?
- [ ] What's the target demo environment - hallway, lab floor, classroom?
- [ ] Are there specific commands/gestures the lecturer wants to see, or is the vocabulary up to the student?
- [ ] Is the OLED display feature in scope, or stretch goal only?

## Tunables needing on-hardware calibration

- [ ] `STEERING_GAIN` - tune so follow-mode steering is responsive but not twitchy.
- [ ] `HAND_SIZE_STOP` / `HAND_SIZE_FAR` - depend on camera FOV and hand-on-floor distance.
- [ ] `SPIN_DIRECTION` - which way should spins rotate by default?
- [ ] `REVERSE_THROTTLE` - is the chosen reverse speed safe in the demo space?
- [ ] `FINGER_STRAIGHTNESS_COS_MIN` - if POINT/OPEN_PALM detection is jittery in follow mode, adjust.

## Decisions deferred

- [ ] In follow mode, should losing the hand pause (current: safety stop after 3 s) or exit follow entirely?
- [ ] Should `come` be re-speakable to extend follow mode without the robot stopping first? (Currently yes - saying `come` again resets the 10 s timer.)
