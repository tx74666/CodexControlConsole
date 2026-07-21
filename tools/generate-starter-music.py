import argparse
import math
import struct
import wave
from pathlib import Path


SAMPLE_RATE = 22_050
DURATION_SECONDS = 24
TRACKS = (
    {
        "name": "Codex - Quiet Circuit.wav",
        "tempo": 92,
        "roots": (48, 45, 41, 43),
        "lead": (0, 4, 7, 11, 7, 4, 2, 7),
        "color": 0.15,
    },
    {
        "name": "Codex - Glass Horizon.wav",
        "tempo": 104,
        "roots": (50, 46, 43, 48),
        "lead": (7, 9, 4, 2, 0, 4, 7, 9),
        "color": 0.7,
    },
    {
        "name": "Codex - Night Workspace.wav",
        "tempo": 78,
        "roots": (45, 41, 48, 43),
        "lead": (0, 7, 4, 11, 9, 4, 2, 7),
        "color": 1.2,
    },
)


def midi_frequency(note):
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def smooth_step(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def deterministic_noise(index, offset):
    value = math.sin((index + 1) * (12.9898 + offset)) * 43_758.5453
    return (value - math.floor(value)) * 2.0 - 1.0


def render_track(output_path, track):
    tempo = float(track["tempo"])
    seconds_per_beat = 60.0 / tempo
    frame_count = SAMPLE_RATE * DURATION_SECONDS
    chord_intervals = (0, 4, 7, 11)
    frames = bytearray()

    for index in range(frame_count):
        time_value = index / SAMPLE_RATE
        beat = time_value / seconds_per_beat
        measure = int(beat // 4)
        measure_beat = beat % 4.0
        root = track["roots"][measure % len(track["roots"])]

        chord_attack = smooth_step(min(measure_beat / 0.65, 1.0))
        chord_release = smooth_step(min((4.0 - measure_beat) / 0.8, 1.0))
        pad_envelope = chord_attack * chord_release
        left = 0.0
        right = 0.0

        for chord_index, interval in enumerate(chord_intervals):
            frequency = midi_frequency(root + interval)
            phase = 2.0 * math.pi * frequency * time_value
            detune = 1.0 + (chord_index - 1.5) * 0.0018
            shimmer = math.sin(2.0 * math.pi * frequency * detune * time_value + track["color"])
            base = math.sin(phase) * 0.72 + math.sin(phase * 0.5) * 0.28
            pan = (chord_index / 3.0) * 0.7 + 0.15
            left += (base * 0.82 + shimmer * 0.18) * (1.0 - pan * 0.35) * 0.075 * pad_envelope
            right += (base * 0.82 + shimmer * 0.18) * (0.65 + pan * 0.35) * 0.075 * pad_envelope

        eighth = beat * 2.0
        eighth_phase = eighth - math.floor(eighth)
        lead_index = int(math.floor(eighth)) % len(track["lead"])
        lead_note = root + 12 + track["lead"][lead_index]
        lead_frequency = midi_frequency(lead_note)
        pluck_envelope = math.exp(-eighth_phase * 5.6)
        pluck_phase = 2.0 * math.pi * lead_frequency * time_value
        pluck = (
            math.sin(pluck_phase)
            + math.sin(pluck_phase * 2.01) * 0.32
            + math.sin(pluck_phase * 3.0) * 0.12
        ) * pluck_envelope * 0.11
        lead_pan = 0.5 + math.sin(2.0 * math.pi * beat / 8.0 + track["color"]) * 0.28
        left += pluck * (1.0 - lead_pan * 0.45)
        right += pluck * (0.55 + lead_pan * 0.45)

        half_beat = beat * 2.0
        drum_phase = half_beat - math.floor(half_beat)
        if int(math.floor(half_beat)) % 4 == 0:
            kick_frequency = 48.0 + 46.0 * math.exp(-drum_phase * 9.0)
            kick = math.sin(2.0 * math.pi * kick_frequency * time_value) * math.exp(-drum_phase * 11.0) * 0.16
            left += kick
            right += kick
        hat = deterministic_noise(index, track["color"]) * math.exp(-drum_phase * 24.0) * 0.018
        left += hat * 0.8
        right += hat

        bass_phase = beat - math.floor(beat)
        bass_frequency = midi_frequency(root - 12)
        bass = math.sin(2.0 * math.pi * bass_frequency * time_value) * math.exp(-bass_phase * 3.2) * 0.12
        left += bass
        right += bass

        fade = min(1.0, time_value / 1.2, (DURATION_SECONDS - time_value) / 1.6)
        fade = smooth_step(fade)
        left = math.tanh(left * fade * 1.45) * 0.82
        right = math.tanh(right * fade * 1.45) * 0.82
        frames.extend(struct.pack("<hh", int(left * 32_767), int(right * 32_767)))

    with wave.open(str(output_path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(frames)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for track in TRACKS:
        render_track(args.output / track["name"], track)
    print(f"Created {len(TRACKS)} starter tracks in {args.output}")


if __name__ == "__main__":
    main()
