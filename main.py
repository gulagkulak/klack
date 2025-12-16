import os
import random
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Any

import pygame
from pynput import keyboard
from pydub import AudioSegment

# =====================
# Configuration
# =====================

# Directory paths for sounds
PROJECT_ROOT = Path(__file__).parent
KEYDOWN_DIR = PROJECT_ROOT / "keydown"
KEYUP_DIR = PROJECT_ROOT / "keyup"
PROCESSED_DIR = PROJECT_ROOT / "processed"
PROC_KEYDOWN_DIR = PROCESSED_DIR / "keydown"
PROC_KEYUP_DIR = PROCESSED_DIR / "keyup"

# Optional gain adjustment in dB for all sounds (0 leaves original volume)
GAIN_DB = 0.0

# If True, ignore auto-repeated keypresses generated when a key is held down
IGNORE_KEY_REPEAT = False

# Preprocessing/output audio format
TARGET_SAMPLE_RATE = 44100
TARGET_CHANNELS = 1  # preprocess as mono; mixer can still output stereo by duplicating
TARGET_SAMPLE_WIDTH = 2  # bytes (16-bit)


# Mixer/output channels (1=mono, 2=stereo duplication). Default 2 to ensure both ears.
def _get_mixer_channels() -> int:
    val = os.getenv("KLACK_CHANNELS", "2").strip()
    if val in {"1", "2"}:
        return int(val)
    return 2


def _debug_enabled() -> bool:
    return os.getenv("KLACK_DEBUG_AUDIO", "0").strip() in {"1", "true", "yes", "on"}


def _ensure_processed_wav(src: Path, dst: Path) -> Optional[Path]:
    """Ensure a WAV version of src exists at dst with target format. Returns dst or None on error."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Skip if up-to-date
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
        seg = AudioSegment.from_file(src)
        if GAIN_DB:
            seg = seg.apply_gain(GAIN_DB)
        # Convert to target format
        seg = (
            seg.set_frame_rate(TARGET_SAMPLE_RATE)
            .set_channels(TARGET_CHANNELS)
            .set_sample_width(TARGET_SAMPLE_WIDTH)
        )
        seg.export(dst, format="wav")
        return dst
    except Exception as e:
        print(f"Failed to preprocess {src}: {e}")
        return None


@dataclass
class Clip:
    # Use a broad type to avoid importing/accessing pygame.mixer at import/annotation time
    sound: Any


class SoundPool:
    """Loads sound files, preprocesses to WAV, and plays them via pygame.mixer with low latency."""

    def __init__(self, keydown_dir: Path, keyup_dir: Path):
        # Preprocess to WAV in processed/ subfolders
        self.keydown_clips: List[Clip] = self._prepare_clips(
            keydown_dir, PROC_KEYDOWN_DIR
        )
        self.keyup_clips: List[Clip] = self._prepare_clips(keyup_dir, PROC_KEYUP_DIR)
        if not self.keydown_clips:
            raise FileNotFoundError(f"No playable sound files found in {keydown_dir}")
        if not self.keyup_clips:
            raise FileNotFoundError(f"No playable sound files found in {keyup_dir}")

        # Track last event times to optionally filter auto-repeat
        self._last_press = {}
        self._last_release = {}

        # pygame mixer handles overlapping playback internally

    def _prepare_clips(self, src_dir: Path, out_dir: Path) -> List[Clip]:
        supported_ext = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
        clips: List[Clip] = []
        if not src_dir.exists():
            return clips
        for entry in sorted(src_dir.iterdir()):
            if not (entry.is_file() and entry.suffix.lower() in supported_ext):
                continue
            dst = out_dir / (entry.stem + ".wav")
            wav = _ensure_processed_wav(entry, dst)
            if not wav:
                continue
            try:
                snd = pygame.mixer.Sound(str(wav))
                clips.append(Clip(sound=snd))
            except Exception as e:
                print(f"Failed to prepare clip {wav}: {e}")
        return clips

    def _play_random(self, clips: List[Clip]):
        clip = random.choice(clips)
        self._play_clip(clip)

    def _play_clip(self, clip: Clip):
        try:
            clip.sound.play()  # non-blocking, supports overlap
        except Exception as e:
            print("pygame.mixer playback failed:", e)

    def on_press(self, key):
        if IGNORE_KEY_REPEAT:
            now = time.time()
            k = getattr(key, "vk", None) or getattr(key, "value", None) or str(key)
            last = self._last_press.get(k, 0)
            # Filter very fast repeats (<5ms) typical for auto-repeat timing queries
            if now - last < 0.005:
                return
            self._last_press[k] = now
        threading.Thread(
            target=self._play_random, args=(self.keydown_clips,), daemon=True
        ).start()

    def on_release(self, key):
        if IGNORE_KEY_REPEAT:
            now = time.time()
            k = getattr(key, "vk", None) or getattr(key, "value", None) or str(key)
            last = self._last_release.get(k, 0)
            if now - last < 0.005:
                return
            self._last_release[k] = now
        threading.Thread(
            target=self._play_random, args=(self.keyup_clips,), daemon=True
        ).start()

    # pygame.mixer requires no explicit mixer start per sound pool


# =====================
# pygame.mixer init
# =====================


def _init_pygame_mixer():
    channels = _get_mixer_channels()
    buf_env = os.getenv("KLACK_MIXER_BUFFER", "512").strip()
    try:
        buffer = max(128, int(float(buf_env)))
    except Exception:
        buffer = 512

    # Pre-init to control exact format before mixer.init()
    pygame.mixer.pre_init(
        frequency=TARGET_SAMPLE_RATE, size=-16, channels=channels, buffer=buffer
    )
    try:
        pygame.mixer.init()  # Uses SDL default device (PipeWire/Pulse on desktop)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize pygame.mixer: {e}")

    if _debug_enabled():
        try:
            freq, fmt, ch = pygame.mixer.get_init()
            drv = os.getenv("SDL_AUDIODRIVER", "(default)")
            print(
                f"[audio] pygame.mixer init: freq={freq} fmt={fmt} channels={ch} buffer={buffer} driver={drv}"
            )
        except Exception:
            pass


def main():
    print("Klack: global key sounds using X11 (pynput). Press Ctrl+C to quit.")
    # Initialize pygame mixer first
    try:
        _init_pygame_mixer()
    except Exception as e:
        print(e)
        return
    # Ensure directories exist
    if not KEYDOWN_DIR.exists() or not KEYUP_DIR.exists():
        print(
            f"Expected directories 'keydown' and 'keyup' next to main.py. Found:\n"
            f"  keydown: {KEYDOWN_DIR.exists()}\n  keyup: {KEYUP_DIR.exists()}"
        )
        return

    try:
        pool = SoundPool(KEYDOWN_DIR, KEYUP_DIR)
    except Exception as e:
        print("Error initializing sounds:", e)
        print(
            "If using MP3/OGG/etc., install ffmpeg so pydub can decode sources during preprocessing."
        )
        return

    # Start keyboard listener (uses Xlib backend on Linux, no root required on X11)
    listener = keyboard.Listener(on_press=pool.on_press, on_release=pool.on_release)
    listener.start()

    try:
        while listener.is_alive():
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        listener.stop()
        try:
            pygame.mixer.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
