"""Synthetic guitar with a known perfect answer (PLAN.md section 8.2).

Render the same notes twice with the same seed: once with ratio=1 (the input)
and once with ratio=r (the target a perfect shifter would give).
"""
import numpy as np

STIFFNESS = 1e-4
PLUCK = 0.18
PICKUP_HZ = 3500.0


def partial_freqs(f0, kmax=40, fmax=8000.0):
    k = np.arange(1, kmax + 1)
    f = k * f0 * np.sqrt(1.0 + STIFFNESS * k * k)
    return f[f < fmax]


def guitar(notes, fs, dur, ratio=1.0, seed=0, decay_scale=1.0, vibrato=None, stop=None, choke=False):
    """notes: list of (f0, start_time, amplitude). vibrato: (rate_hz, depth_cents).
    stop: time at which all strings are muted by hand (5 ms fade).
    choke: every note is on the same string, so a new pick ends the note before it (3 ms fade)."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(dur * fs)) / fs
    y = np.zeros(len(t))
    for f0, t0, amp in notes:
        on = t >= t0
        tt = t[on] - t0
        later = [s for _, s, _ in notes if s > t0]
        ring = np.clip(1.0 - (t[on] - min(later)) / 0.003, 0.0, 1.0) if choke and later else 1.0
        if vibrato:
            rate, cents = vibrato
            dev = 2.0 ** (cents / 1200.0) - 1.0
            # time warp whose derivative is 1 + dev*sin(2*pi*rate*t)
            warp = tt + dev * (1.0 - np.cos(2 * np.pi * rate * tt)) / (2 * np.pi * rate)
        else:
            warp = tt
        attack = np.minimum(1.0, tt / 0.002)
        for k, fk in enumerate(partial_freqs(f0), start=1):
            a = amp * abs(np.sin(k * np.pi * PLUCK)) / k / (1.0 + (fk / PICKUP_HZ) ** 2)
            tau = decay_scale * float(np.clip(3.0 * (100.0 / fk) ** 0.6, 0.05, 4.0))
            phi = rng.uniform(0.0, 2 * np.pi)
            if fk * ratio < 0.45 * fs:
                y[on] += a * attack * ring * np.exp(-tt / tau) * np.cos(2 * np.pi * fk * ratio * warp + phi)
    if stop is not None:
        y *= np.clip(1.0 - (t - stop) / 0.005, 0.0, 1.0)
    return y
