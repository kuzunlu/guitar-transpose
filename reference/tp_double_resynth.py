"""Studio doubler, "analyse and play again" (PLAN.md section 16.8). Research code,
offline, NumPy only.

The doubler so far bends one recording (shift, detune, drift). However well it
bends, a copy keeps the recording's fine detail, and two copies in one speaker
phase against each other. A real second take has new fine detail: every
overtone starts at a new point in its cycle, and the pick and string noise are
new. So this engine takes the recording apart and plays it again, like the
true takes in the tests are made from their note list:

  1. Analyse (the offline transpose engine, tp_offline.Offline, at 0
     semitones): picks, overtone tracks with their level curves, and the
     residual (pick and string noise, whatever the tracks do not explain).
  2. Play a take: every overtone keeps its level and frequency curve, but each
     stretch that starts at a pick gets a new random start phase (a new pluck).
     The residual gets new random detail with the same colour and level.
  3. Timing, pitch, level and tone per pick: tp_double_studio.StudioDoubler,
     with each take's own played-again signal as its source.

Works on the clean DI (user, 2026-11-24): a clean string really is a set of
decaying sines. Each take then goes through its own amp sim, on its own track.
"""
import numpy as np

from tp_double_studio import StudioDoubler, StudioParams
from tp_offline import Offline, attack_start, detect_attacks, detect_stops

NOISE_N = 256            # the residual's new detail: STFT length (5 ms, keeps the pick click short)
NOISE_HOP = 64
NOISE_ENV_MS = 2.0       # the new residual follows the old one's level in windows this long


def new_noise(res, rng):
    """Same colour and level, new detail: random phase in every STFT bin, then
    the short-time level is matched to the original residual."""
    n = len(res)
    w = np.hanning(NOISE_N)
    k = NOISE_N // 2 + 1
    rp = np.concatenate((np.zeros(NOISE_N), res, np.zeros(NOISE_N)))
    out = np.zeros(len(rp))
    for i in range(0, len(rp) - NOISE_N, NOISE_HOP):
        X = np.fft.rfft(w * rp[i: i + NOISE_N])
        out[i: i + NOISE_N] += w * np.fft.irfft(np.abs(X) * np.exp(2j * np.pi * rng.random(k)), NOISE_N)
    out = out[NOISE_N: NOISE_N + n]
    m = max(1, int(NOISE_ENV_MS * 1e-3 * 48000))
    box = np.ones(m) / m
    e_old = np.sqrt(np.convolve(res * res, box, "same"))
    e_new = np.sqrt(np.convolve(out * out, box, "same"))
    return out * e_old / (e_new + 1e-9 * (e_old.max() + 1e-12) + 1e-15)


class Resynth(Offline):
    def __init__(self, p):
        super().__init__(p, 0.0, ring_on=False, split_beats=False)

    def analyse(self, x):
        """Steps 1-2 of Offline.process: picks, cuts, tracks, fit."""
        x = np.asarray(x, dtype=float)
        attacks = sorted(set(attack_start(x, t) for t in detect_attacks(x, self.p.fs)))
        cuts = sorted(set(attacks + detect_stops(x, self.p.fs)))
        tracks = self._tracks(x)
        for t in tracks:
            lo, hi = self._span(t, len(x))
            t["cuts"] = [c for c in cuts if lo < c < hi]
            t["cuts0"] = list(t["cuts"])
        self._other = set()
        self.residual = self._fit(x, tracks)
        self.tracks, self.attacks, self.n = tracks, set(attacks), len(x)
        return self

    def tonal(self, rng=None):
        """The overtones. rng None: the original phases (the fit itself);
        else a new random start phase for every stretch of every track."""
        n, Ha = self.n, self.hop
        out = np.zeros(n + 2 * self.PAD)
        for t in self.tracks:
            if np.abs(t["A"]).max() < 1e-6:
                continue
            tf = t["tf"]
            lo, hi = self._span(t, n)
            a0 = max(lo, int(tf[0]) - Ha)
            a1 = min(hi, int(tf[-1]) + Ha + 1)
            env = self._envelope(t, t["A"], a0, a1)
            psi = self._phase(t, lo, hi)[a0 - lo: a1 - lo] + np.unwrap(np.angle(env))
            # a stretch starts at every pick of this track; a partial that rings
            # through the pick (most of its level kept) keeps its phase
            amp = np.abs(env)
            starts = [a0] + [c for c in t["cuts"] if a0 + 8 < c < a1 - self.blend - 8 and c in self.attacks
                             and amp[c - a0 - 4] < 0.5 * amp[c - a0 + self.blend + 4]]
            sig = np.zeros(a1 - a0)
            for s, b0 in enumerate(starts):
                b1 = starts[s + 1] if s + 1 < len(starts) else a1
                c = 0.0 if rng is None else rng.uniform(0.0, 2.0 * np.pi)
                sl = slice(b0 - a0, b1 - a0)
                sig[sl] = amp[sl] * np.cos(psi[sl] + c)
            out[self.PAD + a0: self.PAD + a1] += sig
        return out[self.PAD: self.PAD + n]

    def take(self, rng):
        """A new take of the same performance, in time with the input."""
        return self.tonal(rng) + new_noise(self.residual, rng)


class ResynthDoubler(StudioDoubler):
    """StudioDoubler whose copies are played-again takes instead of bent copies."""

    def process(self, x):
        x = np.asarray(x, dtype=float)
        mono = x if x.ndim == 1 else x.mean(axis=1)
        rs = Resynth(self.p).analyse(mono)
        rng = np.random.default_rng(self.dp.seed + 7919)
        self.sources = [mono] + [rs.take(np.random.default_rng(rng.integers(1 << 62)))
                                 for _ in range(self.dp.takes - 1)]
        self.resynth = rs
        return super().process(mono)


def resynth_params(**kw):
    """Studio settings for played-again takes: no overtone drift (the takes
    already have new fine detail)."""
    return StudioParams(drift=0.0, **kw)
