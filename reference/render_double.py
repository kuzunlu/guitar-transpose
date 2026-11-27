"""Double a WAV file with the reference doubler, so you can listen to it.

Usage:  python render_double.py in.wav out.wav [name=value ...]

Use an amped guitar track (the doubler goes after the amp sim). Mono or stereo.
The output is stereo and is shifted back by the reported latency (12 samples
in Live, 50 ms in Studio), like Ableton does, so it lines up with the input in
your DAW. Settings are the DoubleParams names, for example:

    python render_double.py riff.wav riff_quad.wav takes=4 timing_ms=12 pitch_cents=8
    python render_double.py riff.wav riff_quad.wav mode=studio takes=4

    mode           live or studio (sees ahead, best quality) default live

    takes          2, 3 or 4 (the original included)      default 2
    timing_ms      timing spread                           default 8
    timing_jitter  0 ... 1, how new each note's timing is  default 0.6
    timing_drift   0 ... 1, slow rushing / dragging        default 0.3
    pitch_cents    pitch spread                            default 6
    pitch_jitter   0 ... 1                                 default 0.6
    wander_cents   pitch movement inside a note            default 1
    level_db       level spread per note                   default 1
    tone           0 ... 1                                 default 0.3
    decorr         0 ... 1, velvet filter (against flanger) default 1
    width          0 ... 1                                 default 1
    copies_db      level of the copies                     default 0
    seed           any whole number; new seed = new takes  default 1
    drift          studio only: 0 ... 3, overtone drift     default 1
                   (studio has decorr 0: the drift replaces the velvet filter)
"""
import sys
import time
from dataclasses import fields

import numpy as np

from tp_double import DoubleParams, Doubler
from tp_double_studio import StudioDoubler, StudioParams
from tp_ref import Params
from wavio import read_wav, write_wav


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src, dst = sys.argv[1], sys.argv[2]
    args = [a.partition("=") for a in sys.argv[3:]]
    studio = any(name == "mode" and value == "studio" for name, _, value in args)
    types = {f.name: f.type for f in fields(StudioParams if studio else DoubleParams)}
    dp = StudioParams() if studio else DoubleParams()
    for name, _, value in args:
        if name == "mode":
            continue
        if name not in types:
            print(f"unknown setting: {name}")
            return 1
        setattr(dp, name, int(value) if types[name] in (int, "int") else float(value))
    x, rate = read_wav(src)
    if x.shape[1] > 2:
        x = x[:, :2]
    p = Params(fs=float(rate))
    t0 = time.time()
    eng = StudioDoubler(p, dp) if studio else Doubler(p, dp)
    y, _ = eng.process(x)
    y = np.concatenate((y[eng.latency:], np.zeros((eng.latency, 2))))
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 1.0:
        print(f"warning: output peaks at {20 * np.log10(peak):+.1f} dBFS and will clip in the file")
    write_wav(dst, y, rate)
    print(f"wrote {dst}: {len(y) / rate:.1f} s, {'studio' if studio else 'live'}, {dp.takes} takes, "
          f"took {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
