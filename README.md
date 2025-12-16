# K L A C K

Inspired by the observation that people with ADHD do better when the sound of what they are doing is amplified.

https://news.stanford.edu/stories/2025/12/wearable-device-audio-augmentation-mindfulness-anxiety-adhd

Uses pygame to play keyboard sounds in an X11 desktop environment.

## Installation

Install uv. Install libsdl2. Needed by pygame to play sounds. Clone this repo. Then:

```shell
uv sync
uv run main.py
```

Enjoy the klack.

## Using custom sounds

Stop the app. Delete the `processed` folder. Put your keydown sounds to the `keydown` folder. Put your keyup sounds to
the `keyup` folder. Run app.

You might want to use symlinks for the above folders so you can swap between different sound sets easily.

The klacks go well with lo-fi background musick.
