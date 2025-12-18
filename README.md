# Klack

Inspired by the observation that people with ADHD do better when the sound of what they are doing is amplified.

https://news.stanford.edu/stories/2025/12/wearable-device-audio-augmentation-mindfulness-anxiety-adhd

Uses pygame to play keyboard sounds in an X11 desktop environment. Now ships as a Linux desktop tray application.

## Installation

Prereqs:

- Install `uv`. You probably want to use apt/emerge or your distro equivalent, but if not, https://docs.astral.sh/uv/
- Install SDL2 libraries (needed by pygame). On Debian/Ubuntu: `sudo apt install libsdl2-2.0-0 libsdl2-mixer-2.0-0`
- You probably already have the needed GTK/GObject dependencies.

Steps:

1. Clone this repository anywhere you like.
2. Test it out with `./run.sh`
3. If you like it, run the installer: `./install.sh`
4. Open your system application launcher and start "Klack".
5. Right click the Klack tray icon to Toggle Sound on/off or Quit.

Enjoy the klack.

## Using custom sounds

Stop the app. Delete the `processed` folder. Put your keydown sounds to the `keydown` folder. Put your keyup sounds in
the `keyup` folder. Run app.

You might want to use symlinks for the above folders so you can swap between different sound sets easily.

The klacks go well with lo-fi background music.

## Scripts

- `run.sh`: single entry point to sync the environment with `uv` and run `main.py`.
- `install.sh`: installs a `klack.desktop` entry pointing to `run.sh` and `icon.svg`, refreshes the desktop cache for
  GNOME/KDE/Cinnamon, and can optionally enable autostart on login.
- `uninstall.sh`: removes the installed desktop entry and autostart entry if present.

## Notes

- System tray support uses `pystray`; a tray should be visible on GNOME/KDE/Cinnamon. On Wayland GNOME, ensure a legacy
  tray is available (e.g., via an extension) if you don't see the icon.
- Keyboard hook uses `pynput` (X11). On Wayland, global key events may be restricted by the compositor.
- Only tested on Cinnamon/Gentoo.