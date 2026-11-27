"""Doubler tests (PLAN.md section 16): our doubler against a plain fixed-delay
doubler and against a true double (the same notes played again).

Usage:  python double_tests.py

Each scenario is a synthetic guitar part with pick noise, run through a
simple amp (tanh distortion + cab low-pass), so it looks like what the plugin
gets after the amp sim. Metrics, for the stereo output (L = original side, R = double side):

  coh low/mid/high  how alike L and R are in 80-300 / 300-2000 / 2000-8000 Hz
                    (1 = one is a copy of the other, 0 = unrelated, like two real takes)
  mono dB           level of L+R against L and R played apart: +3 = copies (comb
                    filter in mono), 0 = unrelated
  comb              comb strength inside L (cepstrum peak of L against the input,
                    0.3-30 ms): high = regular cancel spots = flanger / phaser sound.
                    Matters most for quad, where two takes share a speaker
  bal dB            L level against R level
  lag ms            how late R is on average (envelope match)
  spread ms         spread of the timing between the two takes, per pick (std)
  copy 1st          share of picks where the copy lands before the original
                    (a real double: about half)
  picks             picks found / picks played
"""
import numpy as np

from synth import guitar
from tp_double import DoubleParams, Doubler, detect_picks, fixed_doubler, layout
from tp_ref import Params

FS = 48000
E2, A2, B2, D3, E3, G3, A3, C4, D4, E4 = 82.41, 110.0, 123.47, 146.83, 164.81, 196.0, 220.0, 261.63, 293.66, 329.63


def amp(x):
    y = np.tanh(6.0 * x / (np.max(np.abs(x)) + 1e-12)) * 0.5
    for _ in range(2):                                   # cab: 2 x one-pole at 5 kHz
        a = 1.0 - np.exp(-2.0 * np.pi * 5000.0 / FS)
        z = np.empty(len(y))
        s = 0.0
        for n, v in enumerate(y.tolist()):
            s += a * (v - s)
            z[n] = s
        y = z
    return y


def pick_noise(notes, n, rng):
    """A short noise burst at every pick, as a real pick makes. Scaled to the part."""
    c = np.zeros(n)
    for t in sorted({t for _, t, _ in notes}):
        k = int(t * FS)
        m = min(96, n - k)
        c[k: k + m] += 0.3 * rng.standard_normal(m) * np.exp(-np.arange(m) / 24.0)
    return c


def played(notes, dur, opt, seed, rng):
    g = guitar(notes, FS, dur, seed=seed, **opt)
    return amp(g + np.max(np.abs(g)) * pick_noise(notes, len(g), rng))


def scenarios():
    s16 = 60.0 / 140 / 4
    chug = [(E2, i * s16, 1.0) for i in range(24)]
    chords = [(f, i * 2.0, 1.0) for i, root in enumerate((E2, A2, B2, D3))
              for f in (root, root * 1.4983, root * 2.0)]
    s8 = 60.0 / 150 / 2
    lead = [(f, i * s8, 1.0) for i, f in enumerate((A3, C4, D4, E4, D4, C4, A3, G3, A3, E3, G3, A3))]
    return [("chug", chug, 3.0, dict(decay_scale=0.15, choke=True)),
            ("chords", chords, 8.0, {}),
            ("lead", lead, 5.0, dict(choke=True))]


def true_double(notes, dur, opt, rng):
    """The same part played again: new timing per pick (strings of one strum
    move together, plus a small strum spread), new pitch, level and phases."""
    picks = sorted({t for _, t, _ in notes})
    shift = {t: rng.normal(0.0, 0.004) for t in picks}
    cents = {t: rng.normal(0.0, 3.0) for t in picks}
    again = [(f * 2.0 ** (cents[t] / 1200.0), max(0.0, t + shift[t] + rng.uniform(0.0, 0.0015)),
              a * 10.0 ** (rng.normal(0.0, 1.0) / 20.0)) for f, t, a in notes]
    return played(again, dur, opt, int(rng.integers(1 << 30)), rng)


def coherence(a, b, lo, hi, nfft=4096, hop=1024):
    w = np.hanning(nfft)
    sab = saa = sbb = 0.0
    for i in range(0, len(a) - nfft, hop):
        fa = np.fft.rfft(w * a[i: i + nfft])
        fb = np.fft.rfft(w * b[i: i + nfft])
        sab = sab + fa * np.conj(fb)
        saa = saa + np.abs(fa) ** 2
        sbb = sbb + np.abs(fb) ** 2
    f = np.fft.rfftfreq(nfft, 1.0 / FS)
    band = (f >= lo) & (f < hi)
    return float(np.sum(np.abs(sab[band]) ** 2 / (saa[band] * sbb[band] + 1e-30)) / np.sum(band))


def comb_strength(y, x, nfft=2048, hop=512):
    """Cepstrum of log(|Y|^2 / |X|^2) per frame. Two copies with delay d give
    a peak at quefrency d; independent takes give none. Mean over frames of the
    highest peak between 0.3 and 30 ms."""
    w = np.hanning(nfft)
    f = np.fft.rfftfreq(nfft, 1.0 / FS)
    band = (f > 300) & (f < 6000)
    q = np.arange(nfft) / FS * 1000.0
    qb = (q > 0.3) & (q < 30)
    vals = []
    for i in range(0, min(len(x), len(y)) - nfft, hop):
        px = np.abs(np.fft.rfft(w * x[i: i + nfft])) ** 2
        py = np.abs(np.fft.rfft(w * y[i: i + nfft])) ** 2
        if px[band].sum() < 1e-6:
            continue
        r = np.log(py + 1e-9) - np.log(px + 1e-9)
        r = np.where(band, r - r[band].mean(), 0.0)
        vals.append(np.abs(np.fft.irfft(r))[qb].max())
    return float(np.mean(vals))


def mix(takes, pans):
    """Pan mono takes like the doubler does."""
    out = np.zeros((len(takes[0]), 2))
    norm = np.sqrt(2.0 / len(takes))
    for y, pan in zip(takes, pans):
        a = 0.25 * np.pi * (pan + 1.0)
        out[:, 0] += norm * np.cos(a) * y
        out[:, 1] += norm * np.sin(a) * y
    return out


def envelope(x):
    e = np.sqrt(np.convolve(x * x, np.ones(96) / 96, "same"))
    return e - e.mean()


def lag_ms(left, right, most=0.02):
    m = int(most * FS)
    el, er = envelope(left), envelope(right)
    c = [np.dot(el[m: -m], er[m + k: len(er) - m + k]) for k in range(-m, m + 1)]
    return 1000.0 * (int(np.argmax(c)) - m) / FS


def metrics(y, x, spread=None, first="", picks=""):
    left, right = y[:, 0], y[:, 1]
    el, er = np.sum(left ** 2), np.sum(right ** 2)
    row = [coherence(left, right, 80, 300), coherence(left, right, 300, 2000),
           coherence(left, right, 2000, 8000),
           10 * np.log10(np.sum((left + right) ** 2) / (el + er)),
           10 * np.log10(el / er), lag_ms(left, right)]
    return row + [spread, first, picks, comb_strength(left, x)]


def main():
    p = Params(fs=float(FS))
    dp = DoubleParams()
    rng = np.random.default_rng(3)
    print(f"{'scenario':8} {'system':7} {'coh low':>7} {'mid':>5} {'high':>5} {'mono dB':>7} "
          f"{'comb':>5} {'bal dB':>6} {'lag ms':>6} {'spread ms':>9} {'copy 1st':>8} {'picks':>6}")
    for name, notes, dur, opt in scenarios():
        x = played(notes, dur, opt, 7, rng)
        twin = true_double(notes, dur, opt, rng)
        eng = Doubler(p, dp)
        ours, delays = eng.process(x)
        picks = sorted({int(t * FS) for _, t, _ in notes})
        at = [min(k + 1200, len(x) - 1) for k in picks]     # delay used 25 ms after each pick
        rel = delays[1][at] - delays[0][at]
        spread = float(np.std(rel)) * 1000.0 / FS
        first = f"{100.0 * np.mean(rel < 0):.0f} %"
        found = np.array(detect_picks(x, FS))
        hits = sum(bool(np.any((found >= k) & (found < k + 480))) for k in picks)
        quad, _ = Doubler(p, DoubleParams(takes=4)).process(x)
        true_quad = mix([x, twin] + [true_double(notes, dur, opt, rng) for _ in range(2)], layout(4, 1.0))
        rows = [("fixed", metrics(fixed_doubler(x, p), x)),
                ("ours", metrics(ours, x, spread, first, f"{hits}/{len(picks)}")),
                ("true", metrics(np.stack((x, twin), axis=1), x)),
                ("ours 4", metrics(quad, x)),
                ("true 4", metrics(true_quad, x))]
        for system, r in rows:
            sp = f"{r[6]:9.1f}" if r[6] is not None else f"{'':9}"
            print(f"{name:8} {system:7} {r[0]:7.2f} {r[1]:5.2f} {r[2]:5.2f} {r[3]:+7.2f} {r[9]:5.3f} "
                  f"{r[4]:+6.2f} {r[5]:+6.1f} {sp} {r[7]:>8} {r[8]:>6}")
        # the original's sound is untouched: with no timing spread it is the input, only delayed
        flat_eng = Doubler(p, DoubleParams(timing_ms=0.0))
        flat, _ = flat_eng.process(x)
        d = flat_eng.latency
        err = np.max(np.abs(flat[d:, 0] / np.sqrt(2.0 / dp.takes) - x[: len(x) - d]))
        assert err < 1e-9, f"original side is not the delayed input ({err})"


if __name__ == "__main__":
    main()
