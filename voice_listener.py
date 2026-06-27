"""
Offline voice command recognition.

Vosk reads audio from the default input device via sounddevice and
matches against a fixed grammar of allowed commands (see
config.VOICE_COMMANDS). A background thread keeps the recognizer fed;
the main loop polls `latest()` for the most recent recognized command
and its timestamp.

Designed to be testable standalone on a dev PC before deploying to the
Jetson - run `python3 voice_listener.py` and speak; recognized commands
print to stdout.
"""

import json
import queue
import threading
import time
from typing import Optional, Tuple

import config


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
            print(f"  [{i}] {dev['name']}{tag}")


class VoiceListener:
    def __init__(self,
                 model_path: str = config.VOICE_MODEL_PATH,
                 sample_rate: int = config.VOICE_SAMPLE_RATE,
                 device_index: Optional[int] = config.VOICE_MIC_DEVICE_INDEX,
                 verbose: bool = False):
        self._verbose = verbose
        self._device_index = device_index
        # Lazy imports so the rest of the project stays importable on
        # machines that don't have vosk/sounddevice installed yet.
        import vosk
        # Silences Vosk's verbose log spam during inference.
        vosk.SetLogLevel(-1)

        self._sample_rate = sample_rate
        self._model = vosk.Model(model_path)

        # Constrained grammar: Vosk will only emit phrases from this
        # list. "[unk]" is a special token that lets non-matching audio
        # produce an empty result instead of a forced match.
        grammar = json.dumps(list(config.VOICE_COMMANDS) + ["[unk]"])
        self._recognizer = vosk.KaldiRecognizer(self._model, sample_rate, grammar)
        # Per-word confidence scores are required to filter out the
        # phonetically-close false matches that constrained grammars
        # produce. See VOICE_MIN_CONFIDENCE in config.
        self._recognizer.SetWords(True)

        self._audio_q: "queue.Queue[bytes]" = queue.Queue()
        self._lock = threading.Lock()
        self._last_command: Optional[str] = None
        self._last_command_time: float = 0.0

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        # blocksize=8000 = 0.5 s of audio at 16 kHz - small enough for
        # responsive recognition, big enough to amortise callback cost.
        # device=None lets sounddevice use the OS default; pass an int
        # index (from list_devices()) to select a specific microphone.
        self._stream = sd.RawInputStream(
            samplerate=self._sample_rate,
            blocksize=8000,
            dtype="int16",
            channels=1,
            device=self._device_index,
            callback=self._audio_callback,
        )
        self._stream.start()

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

    # ------------------------------------------------------------ internal

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        # sounddevice calls this from a dedicated audio thread; just
        # forward the bytes - real work happens in _recognize_loop.
        self._audio_q.put(bytes(indata))

    def _recognize_loop(self) -> None:
        while self._running:
            try:
                data = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._recognizer.AcceptWaveform(data):
                result = json.loads(self._recognizer.Result())
                text = result.get("text", "").strip()
                # "[unk]" or empty means non-command speech / silence.
                if not text or text == "[unk]":
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
                with self._lock:
                    self._last_command = text
                    self._last_command_time = time.time()


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
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        listener.stop()
