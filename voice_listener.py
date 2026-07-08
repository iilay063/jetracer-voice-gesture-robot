"""
Offline voice command recognition.

Vosk matches mic audio against a fixed grammar of allowed commands (see
config.VOICE_COMMANDS). A background thread keeps the recognizer fed;
the main loop polls `latest()` for the most recent recognized command
and its timestamp, and `is_healthy()` to verify the mic is still alive.

Robustness notes (voice is the PRIMARY control channel):
- The mic is opened at Vosk's required 16 kHz mono when the device
  supports it; otherwise at the device's native rate/channels, and the
  audio is downmixed + resampled in software. This matters for USB
  wireless mic receivers (like the K9), which often only expose
  44.1/48 kHz stereo.
- The audio queue is bounded: if recognition falls behind real time the
  oldest audio is dropped, so a "stop" spoken now is never stuck behind
  seconds of stale audio.
- A watchdog timestamp is updated on every audio callback. If the
  receiver dies mid-run, `is_healthy()` goes False and the main loop
  stops the robot.
- "stop" gets a fast path: it is acted on from Vosk's *partial* results,
  before the utterance even ends. A false-positive stop is safe; a slow
  stop is not.

Designed to be testable standalone on a dev PC before deploying to the
Jetson - run `python3 voice_listener.py` and speak; recognized commands
print to stdout.
"""

import json
import queue
import threading
import time
from typing import Optional, Tuple

import numpy as np

import config

# Vosk models are trained at 16 kHz; audio is converted to this rate
# before recognition regardless of what the mic hardware delivers.
VOSK_RATE = config.VOICE_SAMPLE_RATE


def list_devices() -> None:
    """Print every audio input device with its index number.

    Run this (or `python3 voice_listener.py --list-devices`) to find the
    right value for config.VOICE_MIC_DEVICE_INDEX or --mic-device.
    """
    import sounddevice as sd
    default_in = sd.default.device[0]
    print("Available audio input devices:")
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            tag = " <- default" if i == default_in else ""
            print(f"  [{i}] {dev['name']}"
                  f"  ({int(dev['default_samplerate'])} Hz){tag}")


class VoiceListener:
    def __init__(self,
                 model_path: str = config.VOICE_MODEL_PATH,
                 device_index: Optional[int] = config.VOICE_MIC_DEVICE_INDEX,
                 verbose: bool = False):
        self._verbose = verbose
        self._device_index = device_index
        # Lazy imports so the rest of the project stays importable on
        # machines that don't have vosk/sounddevice installed yet.
        import vosk
        # Silences Vosk's verbose log spam during inference.
        vosk.SetLogLevel(-1)

        self._model = vosk.Model(model_path)

        # Constrained grammar: Vosk will only emit phrases from this
        # list. "[unk]" is a special token that lets non-matching audio
        # produce an empty result instead of a forced match.
        grammar = json.dumps(list(config.VOICE_COMMANDS) + ["[unk]"])
        self._recognizer = vosk.KaldiRecognizer(self._model, VOSK_RATE, grammar)
        # Per-word confidence scores are required to filter out the
        # phonetically-close false matches that constrained grammars
        # produce. See VOICE_MIN_CONFIDENCE in config.
        self._recognizer.SetWords(True)

        self._audio_q: "queue.Queue[bytes]" = queue.Queue(
            maxsize=config.VOICE_QUEUE_MAX_BLOCKS)
        self._lock = threading.Lock()
        self._last_command: Optional[str] = None
        self._last_command_time: float = 0.0
        # Set on every audio callback; the watchdog reads it.
        self._last_audio_time: float = 0.0
        # Remembers the last partial text so the "stop" fast path fires
        # once per utterance instead of once per audio block.
        self._last_partial: str = ""

        # Filled in by start() once the actual stream format is known.
        self._native_rate: int = VOSK_RATE
        self._channels: int = 1

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        # Preferred format is exactly what Vosk wants: 16 kHz mono.
        # USB wireless receivers frequently reject that, so fall back to
        # the device's native rate (and stereo if mono is refused) and
        # convert in software. Raising here (instead of degrading
        # silently) is intentional: main.py treats a dead mic as fatal.
        attempts = [(VOSK_RATE, 1)]
        info = sd.query_devices(self._device_index, "input")
        native_rate = int(info["default_samplerate"])
        if native_rate != VOSK_RATE:
            attempts.append((native_rate, 1))
        if info["max_input_channels"] >= 2:
            attempts.append((native_rate, 2))

        last_error: Optional[Exception] = None
        for rate, channels in attempts:
            try:
                stream = sd.RawInputStream(
                    samplerate=rate,
                    # Block length in samples scales with the rate so the
                    # latency stays at VOICE_BLOCK_SEC regardless of format.
                    blocksize=int(rate * config.VOICE_BLOCK_SEC),
                    dtype="int16",
                    channels=channels,
                    device=self._device_index,
                    callback=self._audio_callback,
                )
                stream.start()
            except Exception as exc:
                last_error = exc
                continue
            self._stream = stream
            self._native_rate = rate
            self._channels = channels
            break

        if self._stream is None:
            raise RuntimeError(
                f"could not open microphone in any supported format: "
                f"{last_error!r}")

        if self._native_rate != VOSK_RATE or self._channels != 1:
            print(f"[voice] mic runs at {self._native_rate} Hz "
                  f"x{self._channels}ch; converting to {VOSK_RATE} Hz mono")

        self._last_audio_time = time.time()
        self._running = True
        self._thread = threading.Thread(target=self._recognize_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def latest(self) -> Tuple[Optional[str], float]:
        """Most recent recognized command and the time it was heard
        (time.time() value). Returns (None, 0.0) before anything is heard."""
        with self._lock:
            return self._last_command, self._last_command_time

    def is_healthy(self) -> bool:
        """True while the mic is delivering audio and the recognizer
        thread is alive. Goes False if the wireless receiver drops or
        the recognizer crashes - the main loop must stop the robot."""
        if not self._running:
            return False
        return (time.time() - self._last_audio_time) < config.VOICE_WATCHDOG_SEC

    # ------------------------------------------------------------ internal

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        # sounddevice calls this from a dedicated audio thread; just
        # forward the bytes - real work happens in _recognize_loop.
        self._last_audio_time = time.time()
        if status and self._verbose:
            # Overruns/dropouts reported by PortAudio - useful when
            # diagnosing a flaky wireless mic link.
            print(f"[voice] audio status: {status}")
        try:
            self._audio_q.put_nowait(bytes(indata))
        except queue.Full:
            # Recognizer is behind real time: drop the oldest block so
            # recognition tracks what is being said NOW.
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._audio_q.put_nowait(bytes(indata))
            except queue.Full:
                pass

    def _to_vosk_format(self, data: bytes) -> bytes:
        """Downmix to mono and resample to 16 kHz if the mic's native
        format differs. Pure numpy (linear interpolation) - accuracy is
        plenty for speech and it avoids a scipy dependency on the Nano."""
        if self._native_rate == VOSK_RATE and self._channels == 1:
            return data
        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        if self._channels > 1:
            samples = samples.reshape(-1, self._channels).mean(axis=1)
        if self._native_rate != VOSK_RATE:
            n_out = int(len(samples) * VOSK_RATE / self._native_rate)
            x_out = np.linspace(0.0, len(samples) - 1.0, n_out)
            samples = np.interp(x_out, np.arange(len(samples)), samples)
        return samples.astype(np.int16).tobytes()

    def _set_command(self, command: str) -> None:
        with self._lock:
            self._last_command = command
            self._last_command_time = time.time()

    def _recognize_loop(self) -> None:
        try:
            while self._running:
                try:
                    data = self._audio_q.get(timeout=0.1)
                except queue.Empty:
                    continue
                data = self._to_vosk_format(data)

                if not self._recognizer.AcceptWaveform(data):
                    # Mid-utterance: check partial text for "stop" so the
                    # safety-critical command fires without waiting for the
                    # end-of-utterance silence. A false stop is harmless.
                    partial = json.loads(
                        self._recognizer.PartialResult()).get("partial", "")
                    if partial != self._last_partial:
                        self._last_partial = partial
                        if "stop" in partial.split():
                            if self._verbose:
                                print("  fast-stop from partial result")
                            self._set_command("stop")
                    continue

                self._last_partial = ""
                result = json.loads(self._recognizer.Result())
                text = result.get("text", "").strip()
                # "[unk]" or empty means non-command speech / silence.
                if not text or "[unk]" in text:
                    continue
                # Reject the phrase if any word's confidence is below
                # the threshold - one shaky word taints the whole match.
                words = result.get("result", [])
                if not words:
                    continue
                min_conf = min(w.get("conf", 0.0) for w in words)
                if min_conf < config.VOICE_MIN_CONFIDENCE:
                    if self._verbose:
                        print(f"  rejected: {text!r}  (min_conf={min_conf:.2f}"
                              f" < {config.VOICE_MIN_CONFIDENCE})")
                    continue
                if self._verbose:
                    print(f"  accepted: {text!r}  (min_conf={min_conf:.2f})")
                self._set_command(text)
        except Exception as exc:
            # A dead recognizer thread must not look like "listening".
            # is_healthy() returns False once _running is cleared.
            print(f"[voice] recognizer crashed: {exc!r}")
            self._running = False


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(
        description="Standalone smoke test for voice recognition.")
    p.add_argument("--list-devices", action="store_true",
                   help="Print available audio input devices and exit.")
    p.add_argument("--device", type=int, default=None,
                   help="Audio input device index (see --list-devices).")
    a = p.parse_args()

    if a.list_devices:
        list_devices()
        raise SystemExit(0)

    print(f"Loading model from {config.VOICE_MODEL_PATH}...")
    print(f"Vocabulary: {config.VOICE_COMMANDS}")
    print("Speak a command. Ctrl-C to quit.\n")

    # verbose=True prints every match including rejected ones, so you
    # can see the confidence values and tune VOICE_MIN_CONFIDENCE.
    listener = VoiceListener(verbose=True, device_index=a.device)
    listener.start()

    try:
        last_health = True
        while True:
            time.sleep(0.1)
            healthy = listener.is_healthy()
            if healthy != last_health:
                print(f"[voice] mic {'recovered' if healthy else 'LOST'}")
                last_health = healthy
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        listener.stop()
