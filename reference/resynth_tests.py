"""Tests for the "analyse and play again" doubler (PLAN.md section 16.8).

Usage:  python resynth_tests.py

Setup as the user will use it: the doubler works on the clean DI, and every
take goes through its own amp (same simple amp as double_tests.py, one fixed
drive for all takes). Compared on the synthetic parts:

  bend     StudioDoubler (bent copies with overtone drift)
  resynth  ResynthDoubler (played-again copies)
  true     the same notes played again (double_tests.true_double, on the DI)

First a check: the analysis plus the residual must give back the input.
Columns as in studio_tests.py.
"""
import numpy as np

from double_tests import FS, coherence, comb_strength, mix, pick_noise, scenarios
from studio_tests import attack_sharpness
from synth import guitar
from tp_double import layout, onepole_lp
from tp_double_resynth import Resynth, ResynthDoubler, resynth_params
from tp_double_studio import StudioDoubler, StudioParams
from tp_ref import Params


def di(notes, dur, opt, seed, rng):
    g = guitar(notes, FS, dur, seed=seed, **opt)
    return g + np.max(np.abs(g)) * pick_noise(notes, len(g), rng)


def true_di(notes, dur, opt, rng):
    """double_tests.true_double, but the DI (no amp)."""
    picks = sorted({t for _, t, _ in notes})
    shift = {t: rng.normal(0.0, 0.004) for t in picks}
    cents = {t: rng.normal(0.0, 3.0) for t in picks}
    again = [(f * 2.0 ** (cents[t] / 1200.0), max(0.0, t + shift[t] + rng.uniform(0.0, 0.0015)),
              a * 10.0 ** (rng.normal(0.0, 1.0) / 20.0)) for f, t, a in notes]
    return di(again, dur, opt, int(rng.integers(1 << 30)), rng)


def amp(x, drive):
    """The amp of double_tests.py with a fixed drive (6 / peak of the original DI)."""
    y = np.tanh(drive * x) * 0.5
    for _ in range(2):
        y = onepole_lp(y, 5000.0, FS)
    return y


def measure(takes_amped, x_amped, picks):
    n = len(takes_amped)
    y = mix(takes_amped, layout(n, 1.0)) if n > 2 else np.stack(takes_amped, axis=1)
    left, right = y[:, 0], y[:, 1]
    mono = 10 * np.log10(np.sum((left + right) ** 2) / (np.sum(left ** 2) + np.sum(right ** 2)))
    bal = 10 * np.log10(np.sum(left ** 2) / np.sum(right ** 2))
    al, ar = attack_sharpness(y, picks)
    return coherence(left, right, 300, 2000), mono, comb_strength(left, x_amped), bal, al, ar


def main():
    p = Params(fs=float(FS))
    rng = np.random.default_rng(3)
    print("check: tonal (original phases) + residual against the input")
    parts = []
    for name, notes, dur, opt in scenarios():
        x = di(notes, dur, opt, 7, rng)
        rs = Resynth(p).analyse(x)
        err = x - (rs.tonal(None) + rs.residual)
        share = np.sum(rs.residual ** 2) / np.sum(x ** 2)
        print(f"  {name:7} error {10 * np.log10(np.sum(err ** 2) / np.sum(x ** 2)):7.1f} dB, "
              f"residual {10 * np.log10(share):6.1f} dB of the input, tracks {len(rs.tracks)}")
        parts.append((name, notes, dur, opt, x))
    print()
    print(f"{'part':7} {'system':10} {'coh mid':>7} {'mono dB':>7} {'comb':>6} {'L-R dB':>6} {'atk L / R':>11}")
    for name, notes, dur, opt, x in parts:
        drive = 6.0 / np.max(np.abs(x))
        xa = amp(x, drive)
        truth = np.array(sorted({int(t * FS) for _, t, _ in notes}))
        twins = [true_di(notes, dur, opt, rng) for _ in range(3)]
        for takes in (2, 4):
            for label, eng in (("bend", StudioDoubler(p, StudioParams(takes=takes))),
                               ("resynth", ResynthDoubler(p, resynth_params(takes=takes)))):
                eng.process(x)
                lat = eng.latency
                tk = [amp(np.concatenate((s[lat:], np.zeros(lat))), drive) for s in eng.take_signals]
                c, m, cb, bal, al, ar = measure(tk, xa, truth)
                print(f"{name:7} {f'{label} {takes}':10} {c:7.2f} {m:+7.2f} {cb:6.3f} {bal:+6.2f} {al:5.1f} {ar:5.1f}")
            c, m, cb, bal, al, ar = measure([xa] + [amp(t, drive) for t in twins[: takes - 1]], xa, truth)
            print(f"{name:7} {f'true {takes}':10} {c:7.2f} {m:+7.2f} {cb:6.3f} {bal:+6.2f} {al:5.1f} {ar:5.1f}")


if __name__ == "__main__":
    main()
