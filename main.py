import os
import random
import threading
import time
from pathlib import Path
import signal
from dataclasses import dataclass
from typing import List, Optional, Any

# Force GTK backend for pystray BEFORE importing it
# AppIndicator doesn't work in Cinnamon without the appindicator applet
if not os.getenv('PYSTRAY_BACKEND'):
    os.environ['PYSTRAY_BACKEND'] = 'gtk'
    print(f"[tray debug] Set PYSTRAY_BACKEND=gtk before importing pystray")

import pygame
import pystray
from pynput import keyboard
from pydub import AudioSegment
from PIL import Image

print(f"[tray debug] After import, pystray backend would be: {os.getenv('PYSTRAY_BACKEND')}")

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
        if not sound_enabled():
            return
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
        if not sound_enabled():
            return
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


_sound_enabled_flag = True  # Start with sound enabled
_state_lock = threading.Lock()
_stop_event = threading.Event()
_tray_icon: Optional[pystray.Icon] = None


def sound_enabled() -> bool:
    with _state_lock:
        return _sound_enabled_flag


def set_sound_enabled(val: bool) -> None:
    global _sound_enabled_flag
    with _state_lock:
        _sound_enabled_flag = val


def _get_icon_path() -> Path:
    """Return path to icon file. Prefer PNG for better compatibility."""
    # PNG works better with GTK StatusIcon
    png_path = PROJECT_ROOT / "icon.png"
    if png_path.exists():
        return png_path
    # Fallback to SVG (works with AppIndicator)
    svg_path = PROJECT_ROOT / "icon.svg"
    if svg_path.exists():
        return svg_path
    return None


def _toggle_sound_action(icon, item):
    set_sound_enabled(not sound_enabled())
    # Update menu checkmark/state by recreating and refreshing the menu
    icon.menu = _build_menu()
    try:
        icon.update_menu()
    except Exception:
        # Some backends update automatically when menu is reassigned
        pass


def _quit_action(icon, item):
    _stop_event.set()
    try:
        icon.visible = False
    except Exception:
        pass
    try:
        icon.stop()
    except Exception:
        pass


def _build_menu() -> pystray.Menu:
    toggle_text = "Toggle Sound"
    # Use checked state based on current flag
    return pystray.Menu(
        pystray.MenuItem(
            toggle_text,
            _toggle_sound_action,
            checked=lambda item: sound_enabled(),
            default=True,  # Primary click activates toggle on some backends
        ),
        pystray.MenuItem("Quit", _quit_action),
    )


def _backend_name() -> str:
    try:
        impl = getattr(pystray, "_impl", None)
        print(f"[tray debug] pystray._impl = {impl}")
        if impl is None:
            # Try to detect what pystray would use
            try:
                import gi
                print(f"[tray debug] gi (PyGObject) available: {gi}")
            except ImportError:
                print("[tray debug] gi (PyGObject) NOT available")
            return "unknown"
        name = getattr(impl, "__name__", str(impl))
        print(f"[tray debug] backend name = {name}")
        return name
    except Exception as e:
        print(f"[tray debug] Exception getting backend: {e}")
        return "unknown"


def _tray_setup(icon: pystray.Icon):
    # Ensure properties are set from within setup for GTK/AppIndicator
    try:
        backend = _backend_name()
        print(f"[tray] setup backend={backend}")
    except Exception as e:
        print(f"[tray] Exception in _backend_name: {e}")
        backend = "unknown"

    # Load icon as PIL Image (required by pystray GTK backend)
    icon_path = _get_icon_path()
    print(f"[tray debug] icon_path = {icon_path}")
    print(f"[tray debug] icon_path exists = {icon_path.exists() if icon_path else 'N/A'}")

    if icon_path and icon_path.exists():
        print(f"[tray debug] Loading icon as PIL Image from: {icon_path}")
        try:
            pil_image = Image.open(icon_path)
            print(f"[tray debug] PIL Image loaded: size={pil_image.size}, mode={pil_image.mode}")
            icon.icon = pil_image
            print(f"[tray debug] icon.icon set to PIL Image successfully")
        except Exception as e:
            print(f"[tray debug] Failed to load icon as PIL Image: {e}")
    else:
        print("[tray] Warning: icon file not found, tray icon may not display properly")

    icon.title = "Klack"
    print(f"[tray debug] Set icon.title to: {icon.title}")
    icon.menu = _build_menu()
    print(f"[tray debug] Set icon.menu to: {icon.menu}")

    # Force visibility
    try:
        icon.visible = True
        print(f"[tray debug] Set icon.visible = True")
    except Exception as e:
        print(f"[tray debug] Could not set icon.visible: {e}")


def _run_tray_mainloop():
    """Create the tray icon and run it on the main thread.
    Many GTK/AppIndicator environments require the UI loop to be on the main thread
    for menus to work reliably (e.g., Cinnamon, GNOME).
    """
    global _tray_icon

    print(f"[tray debug] Creating pystray.Icon...")
    print(f"[tray debug] PYSTRAY_BACKEND env = {os.getenv('PYSTRAY_BACKEND', '(not set)')}")

    _tray_icon = pystray.Icon("klack")
    print(f"[tray debug] Icon created: {_tray_icon}")
    print(f"[tray debug] Icon type: {type(_tray_icon)}")
    print(f"[tray debug] Icon class module: {type(_tray_icon).__module__}")
    print(f"[tray] backend={_backend_name()}")

    # Check what's actually available in pystray
    print(f"[tray debug] pystray module file: {pystray.__file__}")
    print(f"[tray debug] pystray version: {getattr(pystray, '__version__', 'unknown')}")

    print(f"[tray debug] Starting icon.run()...")
    _tray_icon.run(setup=_tray_setup)


def main():
    print(
        "Klack: global key sounds using X11 (pynput). Right-click tray icon for menu. Press Ctrl+C to quit."
    )
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

    # Signal handlers for clean quit
    def _handle_sig(signum, frame):
        _stop_event.set()
        # Request the tray loop to stop from a separate thread to avoid signal/GTK issues
        if _tray_icon is not None:
            threading.Thread(target=lambda: _tray_icon.stop(), daemon=True).start()

    try:
        signal.signal(signal.SIGINT, _handle_sig)
        signal.signal(signal.SIGTERM, _handle_sig)
    except Exception:
        pass

    # Run the tray UI loop on the main thread; this returns when icon.stop() is called
    _run_tray_mainloop()
    # Clean shutdown after the tray loop has stopped
    listener.stop()
    try:
        pygame.mixer.quit()
    except Exception:
        pass
    if _tray_icon is not None:
        try:
            _tray_icon.visible = False
            _tray_icon.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
