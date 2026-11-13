"""Transpose a WAV file with a reference engine, so you can listen to it.

Usage:  python render.py in.wav out.wav <semitones> [engine]

engine:  M  predictive engine, the Live design (default)
         A  varispeed only (what the hardware pedals are close to)
         O  offline "Perfect" engine (PLAN.md 5.8): slow, best quality

The input is mixed to mono. M takes about 5 seconds of work per second of
audio; O takes longer (about 5-10 seconds per second for a chord, more for
dense playing). M and A output start `latency` samples late, like the plugin
will. O's output is shifted back, so it lines up with the input exactly.
"""
import sys
import time

import numpy as np

from tp_offline import Offline
from tp_ref import Params, Predictive, engine_a
from wavio import read_wav, write_wav


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    src, dst, semitones = sys.argv[1], sys.argv[2], float(sys.argv[3])
    engine = sys.argv[4] if len(sys.argv) > 4 else "M"
    x, rate = read_wav(src)
    mono = x.mean(axis=1)
    p = Params(fs=float(rate))
    if rate != 48000:
        print(f"note: sizes are tuned for 48000 Hz; this file is {rate} Hz")
    t0 = time.time()
    if engine == "A":
        y, latency = engine_a(mono, p, semitones)
    elif engine == "O":
        eng = Offline(p, semitones)
        y = eng.process(mono)
        y = np.concatenate((y[eng.latency:], np.zeros(eng.latency)))   # offline: no latency
        latency = 0
    else:
        eng = Predictive(p, semitones)
        y, latency = eng.process(mono), eng.latency
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 1.0:
        print(f"warning: output peaks at {20 * np.log10(peak):+.1f} dBFS and will clip in the file")
    write_wav(dst, y, rate)
    print(f"wrote {dst}: {len(y) / rate:.1f} s, engine {engine}, {semitones:+g} semitones, "
          f"latency {latency} samples ({1000.0 * latency / rate:.1f} ms), took {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
