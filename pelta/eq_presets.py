"""Export the Armoury Crate ROG Pelta EQ presets as EasyEffects output presets.

On Windows the Pelta EQ is a software effect (ASUS audio APO), not stored in the
headset, so on Linux it belongs in EasyEffects. Slider values are 0-24 with 12 = flat
(1 dB per step).
"""

import json
from pathlib import Path

FREQS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

PRESETS = {
    "Classic": [12, 12, 18, 18, 12, 12, 12, 12, 14, 14],
    "Hip hop": [11, 16, 17, 13, 11, 11, 12, 12, 16, 16],
    "Jazz": [12, 12, 12, 15, 15, 15, 12, 14, 16, 16],
    "Metal": [8, 12, 12, 12, 12, 12, 15, 12, 15, 13],
    "Rock": [11, 13, 14, 15, 11, 11, 12, 12, 16, 16],
    "Techno": [6, 13, 16, 11, 11, 10, 12, 12, 17, 17],
    "Vocal": [10, 12, 14, 13, 12, 12, 12, 12, 10, 7],
    "FPS": [12, 13, 12, 10, 10, 13, 14, 16, 14, 13],
    "Racing": [12, 19, 15, 12, 14, 14, 12, 12, 9, 7],
}

PRESET_DIR = Path.home() / ".local/share/easyeffects/output"


def _band(freq, gain):
    return {"frequency": float(freq), "gain": float(gain), "mode": "RLC (BT)", "mute": False,
            "q": 1.41, "slope": "x1", "solo": False, "type": "Bell", "width": 4.0}


def preset_json(values):
    gains = [v - 12 for v in values]
    bands = {f"band{i}": _band(f, g) for i, (f, g) in enumerate(zip(FREQS, gains))}
    return {"output": {
        "blocklist": [],
        "plugins_order": ["equalizer#0"],
        "equalizer#0": {
            "balance": 0.0, "bypass": False, "decramp": "Off",
            # pre-attenuate by the largest boost so the EQ cannot clip
            "input-gain": -float(max(0, *gains)), "output-gain": 0.0,
            "mode": "IIR", "num-bands": len(FREQS), "pitch-left": 0.0, "pitch-right": 0.0,
            "split-channels": False, "left": bands, "right": bands,
        },
    }}


def export(directory=PRESET_DIR):
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, values in PRESETS.items():
        path = directory / f"ROG Pelta - {name}.json"
        path.write_text(json.dumps(preset_json(values), indent=4))
        written.append(path)
    return written
