"""Studio doubler tests (PLAN.md section 16.7): Live and Studio against a true
double and a true quad, on the parts of double_tests.py.

Usage:  python studio_tests.py

Columns as in double_tests.py, plus:
  picks       picks found / played, and false finds
  copy 1st    share of picks where take 2 lands before take 1 (a real double: about half)
  spread ms   spread of the timing between take 2 and take 1 at the attacks (std)
  L-R dB      level of the left side against the right (0 = balanced; the user heard a left lean)
  atk L / R   attack sharpness per side: energy above 1.5 kHz in the 5 ms after each attack
              over the 5 ms before it, dB, median. Smeared attacks score low.
"""
import numpy as np

from double_tests import FS, coherence, comb_strength, mix, played, scenarios, true_double
from tp_double import DoubleParams, Doubler, detect_picks, layout, onepole_lp
from tp_double_studio import StudioDoubler, StudioParams, find_picks
from tp_ref import Params


def attack_offsets(delays, picks):
    """Timing of take 2 against take 1 at each pick, in samples: the delay each
    take uses when its read head is 1 ms into the attack."""
    rel = []
    for P in picks:
        d = []
        for dl in delays[:2]:
            t = np.arange(len(dl))
            k = np.nonzero(t - dl >= P + 48)[0]
            d.append(dl[k[0]] if len(k) else np.nan)
        rel.append(d[1] - d[0])
    return np.array(rel)


def attack_sharpness(y, picks):
    """Per side. The attack is searched per side within +-30 ms of the pick
    (steepest rise of the high-band level), because takes land at different times."""
    out = []
    for ch in (0, 1):
        h = y[:, ch] - onepole_lp(y[:, ch], 1500.0, FS)
        h = (h - onepole_lp(h, 1500.0, FS)) ** 2
        e = np.convolve(h, np.ones(48) / 48, "same")
        sh = []
        for P in picks:
            lo, hi = P - 1440, P + 1440
            if lo < 300 or hi + 300 > len(e):
                continue
            k = lo + int(np.argmax(np.diff(e[lo:hi])))
            sh.append(10 * np.log10((h[k: k + 240].sum() + 1e-12) / (h[k - 240: k].sum() + 1e-12)))
        out.append(float(np.median(sh)))
    return out


def row(y, x, lat, picks):
    y = y[lat:]
    x = x[: len(y)]
    left, right = y[:, 0], y[:, 1]
    mono = 10 * np.log10(np.sum((left + right) ** 2) / (np.sum(left ** 2) + np.sum(right ** 2)))
    bal = 10 * np.log10(np.sum(left ** 2) / np.sum(right ** 2))
    return (coherence(left, right, 300, 2000), mono, comb_strength(left, x), bal) + tuple(attack_sharpness(y, picks))


def main():
    p = Params(fs=float(FS))
    rng = np.random.default_rng(3)
    print(f"{'part':7} {'system':12} {'coh mid':>7} {'mono dB':>7} {'comb':>6} {'L-R dB':>6} {'atk L / R':>11} "
          f"{'copy 1st':>8} {'spread ms':>9} {'picks':>10}")
    for name, notes, dur, opt in scenarios():
        x = played(notes, dur, opt, 7, rng)
        twins = [true_double(notes, dur, opt, rng) for _ in range(3)]
        truth = np.array(sorted({int(t * FS) for _, t, _ in notes}))
        found = {"live": np.array(detect_picks(x, FS)), "studio": np.array(find_picks(x, FS))}
        for takes in (2, 4):
            for mode in ("live", "studio"):
                if mode == "live":
                    eng = Doubler(p, DoubleParams(takes=takes))
                else:
                    eng = StudioDoubler(p, StudioParams(takes=takes))
                y, delays = eng.process(x)
                rel = attack_offsets(delays, truth)
                first = f"{100 * np.nanmean(rel < 0):.0f} %"
                spread = f"{1000 * np.nanstd(rel) / FS:9.1f}"
                o = found[mode]
                hits = sum(bool(np.any(np.abs(o - k) < 480)) for k in truth)
                false = sum(bool(np.min(np.abs(truth - q)) >= 480) for q in o)
                c, m, cb, bal, al, ar = row(y, x, eng.latency, truth)
                print(f"{name:7} {f'{mode} {takes}':12} {c:7.2f} {m:+7.2f} {cb:6.3f} {bal:+6.2f} {al:5.1f} {ar:5.1f} "
                      f"{first:>8} {spread} {f'{hits}/{len(truth)} +{false}':>10}")
            true = np.stack((x, twins[0]), axis=1) if takes == 2 else mix([x] + twins, layout(4, 1.0))
            c, m, cb, bal, al, ar = row(true, x, 0, truth)
            print(f"{name:7} {f'true {takes}':12} {c:7.2f} {m:+7.2f} {cb:6.3f} {bal:+6.2f} {al:5.1f} {ar:5.1f}")


if __name__ == "__main__":
    main()
