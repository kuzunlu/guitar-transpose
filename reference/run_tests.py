"""Run the reference engines on synthetic signals and print the numbers.

Usage:  python run_tests.py [basic] [sine] [coh] [scen] [name-filter]
With no arguments, everything runs.
"""
import sys
import time

import numpy as np

from metrics import distort, onset_time, partial_stats, spec_distance, worst_spur_dbc
from synth import guitar, partial_freqs
from tp_offline import Offline
from tp_ref import Hybrid, Params, Predictive, engine_a

P = Params()
FS = P.fs
# A = varispeed only, B = bin-moving phase vocoder, H = B + mask (PLAN 5.4),
# M = predictive engine (PLAN 5.6), M1 = M with every peak modelled at once
# L = M with look-ahead (measuring window centred on now; PLAN 5.8). Add "look" to run it.
# O = offline engine (tp_offline.py, PLAN 5.8). Add "off" to run A, M and O.
ENGINES = ("A", "B", "H", "M") if "all" in sys.argv else ("A", "M", "L") if "look" in sys.argv \
    else ("A", "M", "O") if "off" in sys.argv else ("A", "M")
E2, B2, E3, GS3, B3, E4, A3 = 82.41, 123.47, 164.81, 207.65, 246.94, 329.63, 220.0
A1, B1, FS2 = 55.0, 61.74, 92.50                      # 7-string: drop A, low B, F#2


def db(x):
    return 20.0 * np.log10(max(x, 1e-15))


def run(engine, x, st):
    if engine == "A":
        return engine_a(x, P, st)
    if engine == "O":
        eng = Offline(P, st)
        y = eng.process(x)
        run.debug = {"mask_log": [], "jumps": eng.debug["jumps"], "offline": eng.debug}
        return y, eng.latency
    if engine == "L":
        eng = Predictive(P, st, lookahead=True)
    elif engine in ("M", "M1"):
        eng = Predictive(P, st, mode="adaptive" if engine == "M" else "allmodel")
    else:
        eng = Hybrid(P, st, mode={"B": "tonal", "H": "adaptive"}[engine])
    y = eng.process(x)
    run.debug = eng.debug
    return y, eng.latency


def align(y, lat):
    return np.concatenate((y[lat:], np.zeros(lat)))


def test_basic():
    print("\n== basic: nothing is lost, delay is what we report ==")
    rng = np.random.default_rng(1)
    x = rng.standard_normal(24000) * 0.1
    for mode in ("tonal", "residual"):
        eng = Hybrid(P, 0.0, mode=mode)
        y = eng.process(x)
        lat = eng.latency
        err = y[lat:] - x[: len(x) - lat]
        print(f"  r=1 {mode:9s} latency {lat:4d} samples   error {db(np.sqrt(np.mean(err**2)) / 0.1):7.1f} dB")
    imp = np.zeros(4800)
    imp[1000] = 1.0
    for name in ("A", "B", "H"):
        y, lat = run(name, imp, 0.0)
        print(f"  impulse engine {name}: reported {lat:4d}, measured {int(np.argmax(np.abs(y))) - 1000:4d}")


def test_sine():
    print("\n== sine purity: 997 Hz, -1 semitone (gate: spurs below -60 dBc, pitch within 2 cents) ==")
    t = np.arange(int(1.6 * FS)) / FS
    x = 0.5 * np.sin(2 * np.pi * 997.0 * t)
    r = 2.0 ** (-1 / 12.0)
    tgt = 0.5 * np.sin(2 * np.pi * 997.0 * r * t)
    cases = [("A", None), ("B", True), ("B", False), ("H", True)]
    for name, fo in cases:
        if name == "A":
            y, lat = engine_a(x, P, -1.0)
        else:
            eng = Hybrid(P, -1.0, mode={"B": "tonal", "H": "adaptive"}[name], first_order=fo)
            y, lat = eng.process(x), eng.latency
        spur, f_spur = worst_spur_dbc(y, FS, 997.0 * r)
        cents, wob, lvl = partial_stats(align(y, lat), tgt, FS, 997.0 * r, 0.5, 1.4)
        label = name + ("" if fo is None else (" first-order" if fo else " whole-bin"))
        print(f"  {label:14s} pitch {cents:+6.2f} c   level {lvl:+5.2f} dB   wobble {wob:5.3f} dB   "
              f"worst spur {spur:6.1f} dBc at {f_spur:7.1f} Hz")


def test_coherence():
    print("\n== hand-over: half of each tone in each path; they must add up (gate: within 0.5 dB) ==")
    t = np.arange(int(0.6 * FS)) / FS
    for st in (-2.0, -5.0, 2.0):
        r = 2.0 ** (st / 12.0)
        for f in (110.0, 440.0, 1000.0, 3000.0):
            x = 0.5 * np.sin(2 * np.pi * f * t)
            tgt = 0.5 * np.sin(2 * np.pi * f * r * t)
            row = []
            for m in (0.5, 0.3):
                eng = Hybrid(P, st, mode="fixed", fixed_mask=m)
                y = align(eng.process(x), eng.latency)
                _, wob, lvl = partial_stats(y, tgt, FS, f * r, 0.15, 0.5)
                row.append(f"mask {m}: level {lvl:+5.2f} dB wobble {wob:4.2f} dB jumps {eng.debug['jumps']:2d}")
            print(f"  {st:+.0f} st  {f:6.0f} Hz   " + "   ".join(row))


SCENARIOS = [
    # name, notes, duration, semitones, extra synth options
    ("single note E2  -2", [(E2, 0.1, 0.5)], 1.5, -2, {}),
    ("power chord E5  -5", [(E2, 0.1, 0.4), (B2, 0.1, 0.4)], 1.5, -5, {}),
    ("open E chord    -2", [(f, 0.1, 0.2) for f in (E2, B2, E3, GS3, B3, E4)], 2.0, -2, {}),
    ("open E chord    -5", [(f, 0.1, 0.2) for f in (E2, B2, E3, GS3, B3, E4)], 2.0, -5, {}),
    # choke: each pick ends the note before it, like a real string that is picked again
    ("palm mutes 200  -2", [(E2, 0.1 + 0.075 * i, 0.5) for i in range(12)], 1.1, -2, {"decay_scale": 0.1, "choke": True}),
    ("same string run -2", [(f, 0.1 + 0.15 * i, 0.5) for i, f in enumerate((E2, 87.31, 92.50, 98.0, 92.50, 87.31, E2))],
     1.4, -2, {"choke": True}),
    ("strum+late note -2", [(f, 0.1 + 0.015 * i, 0.2) for i, f in enumerate((E2, B2, E3, GS3, B3))]
     + [(E4, 0.8, 0.3)], 1.6, -2, {}),
    ("vibrato A3      -2", [(A3, 0.1, 0.5)], 1.5, -2, {"vibrato": (5.0, 30.0)}),
    ("chord hand-stop -2", [(f, 0.1, 0.2) for f in (E2, B2, E3, GS3, B3, E4)], 1.2, -2, {"stop": 0.8}),
    ("chord hand-stop -5", [(f, 0.1, 0.2) for f in (E2, B2, E3, GS3, B3, E4)], 1.2, -5, {"stop": 0.8}),
    ("7str low B1     -2", [(B1, 0.1, 0.5)], 1.5, -2, {}),
    ("7str B5 chord   -2", [(B1, 0.1, 0.4), (FS2, 0.1, 0.4)], 1.5, -2, {}),
    ("7str B5 chord   -5", [(B1, 0.1, 0.4), (FS2, 0.1, 0.4)], 1.5, -5, {}),
    ("7str dropA A5   -2", [(A1, 0.1, 0.4), (82.41, 0.1, 0.4)], 1.5, -2, {}),
    ("single note E2  +2", [(E2, 0.1, 0.5)], 1.5, 2, {}),
    ("open E chord    +2", [(f, 0.1, 0.2) for f in (E2, B2, E3, GS3, B3, E4)], 2.0, 2, {}),
]


def test_scenarios(name_filter):
    print("\n== guitar scenarios ==")
    print("  attack = how late the first attack is (ms). cents = mean pitch error. wobble = level wobble of")
    print("  steady partials (dB, mean / worst). spec = distance to the perfect answer (dB). dist = same, after distortion.")
    print("  fine = spec on a 2.9 Hz frequency grid (fair for dense chords, blind to timing).")
    for name, notes, dur, st, opt in SCENARIOS:
        if name_filter and name_filter not in name:
            continue
        r = 2.0 ** (st / 12.0)
        x = guitar(notes, FS, dur, 1.0, seed=7, **opt)
        tgt = guitar(notes, FS, dur, r, seed=7, **opt)
        # only score partials that stand alone: in a chord many partials of
        # different notes sit a few Hz apart and beat, which this measure cannot split
        every = [f * r for f0, _, _ in notes for f in partial_freqs(f0)]
        freqs = sorted(f * r for f0, _, _ in notes for f in partial_freqs(f0)[:8])
        freqs = [f for f in freqs if sum(abs(f - g) < 25.0 for g in every) == 1]
        t_last = max(t0 for _, t0, _ in notes)
        t_tgt = onset_time(tgt, FS, notes[0][1])
        print(f"\n  {name}")
        for eng in ENGINES:
            t0 = time.time()
            y, lat = run(eng, x, float(st))
            secs = time.time() - t0
            attack = (onset_time(y, FS, notes[0][1]) - t_tgt) / FS * 1000.0
            ya = align(y, lat)
            cents, wob = [], []
            if "vibrato" not in opt and "decay_scale" not in opt:
                t_end = opt["stop"] - 0.05 if "stop" in opt else dur - 0.15
                for f in freqs:
                    stt = partial_stats(ya, tgt, FS, f, t_last + 0.2, t_end)
                    if stt:
                        cents.append(abs(stt[0]))
                        wob.append(stt[1])
            sd = spec_distance(ya, tgt, FS)
            sdd = spec_distance(distort(ya), distort(tgt), FS)
            # fine frequency grid (2.9 Hz): partials are kept apart, so their phases matter much less
            sdl = spec_distance(ya, tgt, FS, sizes=(16384,))
            pw = (f"cents {np.mean(cents):5.2f}   wobble {np.mean(wob):5.2f} / {np.max(wob):5.2f}"
                  if cents else "cents   -     wobble   -   /   -  ")
            extra = ""
            if "stop" in opt:
                # sound left over after the strings were muted, against the sound before
                s0 = int(opt["stop"] * FS)
                before = np.mean(ya[s0 - int(0.15 * FS): s0] ** 2)
                tails = [10 * np.log10(np.mean(ya[s0 + int(a_ * FS): s0 + int(b_ * FS)] ** 2) / before + 1e-12)
                         for a_, b_ in ((0.01, 0.03), (0.03, 0.08), (0.08, 0.2))]
                extra = "   left over 10-30 / 30-80 / 80-200 ms: " + " / ".join(f"{v:5.1f}" for v in tails) + " dB"
            if eng == "O":
                od = run.debug["offline"]
                extra += f"   tracks {od['tracks']} split {od['split']}  attacks {od['attacks']} stops {od['stops']}" \
                    f"  cuts joined {od['joined']}" \
                    f"  left after each round (dB): " \
                    + " ".join(f"{v:.1f}" for v in od["residual_db"][1:])
            if eng in ("H", "M", "L"):
                ml = run.debug["mask_log"]
                tonal_at = [f"{m:.2f}" for e, m in ml if e in range(int(0.9 * dur * FS), int(0.9 * dur * FS) + 8 * P.H)]
                extra += f"   jumps {run.debug['jumps']}  tonal share near end {tonal_at[:1]}"
            print(f"    {eng}: attack {attack:5.2f} ms   {pw}   spec {sd:5.2f}   fine {sdl:5.2f}   dist {sdd:5.2f}   ({secs:4.1f} s){extra}")


if __name__ == "__main__":
    args = sys.argv[1:]
    groups = [a for a in args if a in ("basic", "sine", "coh", "scen")]
    filt = next((a for a in args if a not in ("basic", "sine", "coh", "scen", "all", "look", "off")), None)
    if not groups or "basic" in groups:
        test_basic()
    if not groups or "sine" in groups:
        test_sine()
    if not groups or "coh" in groups:
        test_coherence()
    if not groups or "scen" in groups:
        test_scenarios(filt)
