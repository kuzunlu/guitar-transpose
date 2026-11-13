"""Measurements (PLAN.md section 8.3). NumPy only."""
import numpy as np


def partial_track(x, fs, f, win=0.1, hop=0.005):
    """Complex amplitude of the partial at frequency f over time."""
    L = int(win * fs)
    w = np.hanning(L)
    step = int(hop * fs)
    idx = np.arange(0, len(x) - L, step)
    n = idx[:, None] + np.arange(L)[None, :]
    z = (x[n] * np.exp(-2j * np.pi * f * n / fs) * w).sum(axis=1) * 2.0 / w.sum()
    return (idx + L / 2) / fs, z


def partial_stats(out, tgt, fs, f, t_from, t_to, hop=0.005):
    """(pitch error in cents, wobble in dB, level error in dB) of one partial."""
    t, zo = partial_track(out, fs, f, hop=hop)
    _, zt = partial_track(tgt, fs, f, hop=hop)
    sel = (t >= t_from) & (t <= t_to) & (np.abs(zt) > 1e-4)
    if sel.sum() < 8:
        return None
    ratio_db = 20.0 * np.log10(np.abs(zo[sel]) / np.abs(zt[sel]) + 1e-12)
    dphi = np.angle(zo[sel][1:] * np.conj(zo[sel][:-1]))
    f_dev = np.median(dphi) / (2 * np.pi * hop)
    cents = 1200.0 * np.log2((f + f_dev) / f)
    return cents, float(np.std(ratio_db)), float(np.mean(ratio_db))


def onset_time(x, fs, t0, search=0.06):
    """First sample after t0 - 20 ms where |x| passes 10 % of the early peak."""
    a = max(0, int((t0 - 0.02) * fs))
    b = min(len(x), int((t0 + search) * fs))
    seg = np.abs(x[a:b])
    return a + int(np.argmax(seg > 0.1 * seg.max()))


def spec_distance(out, tgt, fs, sizes=(256, 1024, 4096), floor_db=-70.0):
    """Mean absolute log-magnitude difference in dB over several STFT sizes."""
    total = 0.0
    ref = max(np.abs(tgt).max(), 1e-9)
    for n in sizes:
        w = np.hanning(n)
        idx = np.arange(0, min(len(out), len(tgt)) - n, n // 4)
        fr = idx[:, None] + np.arange(n)[None, :]
        a = np.abs(np.fft.rfft(out[fr] * w, axis=1)) * 2.0 / w.sum()
        b = np.abs(np.fft.rfft(tgt[fr] * w, axis=1)) * 2.0 / w.sum()
        fl = ref * 10.0 ** (floor_db / 20.0)
        total += float(np.mean(np.abs(20.0 * np.log10(np.maximum(a, fl)) - 20.0 * np.log10(np.maximum(b, fl)))))
    return total / len(sizes)


def worst_spur_dbc(x, fs, f_main, n=32768, guard_hz=40.0):
    """Largest spectral line away from the main tone, relative to it."""
    w = np.hanning(n)
    m = np.abs(np.fft.rfft(x[-n:] * w))
    fr = np.arange(len(m)) * fs / n
    main = m[np.abs(fr - f_main) < guard_hz].max()
    other = m[(np.abs(fr - f_main) >= guard_hz) & (fr > 20.0)]
    k = int(np.argmax(other))
    f_other = fr[(np.abs(fr - f_main) >= guard_hz) & (fr > 20.0)][k]
    return 20.0 * np.log10(other[k] / main + 1e-15), float(f_other)


def distort(x):
    """A crude high-gain stage, to show what an amp would reveal."""
    return np.tanh(30.0 * x)
