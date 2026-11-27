"""Studio mode of the doubler (PLAN.md section 16.7). Slow, offline, NumPy only.

Live mode (tp_double.py) must decide at once. Studio mode may look ahead, and
the plugin reports a large latency that Ableton removes on playback. Latency
does not matter here, only quality. What the look-ahead buys:

1. Every pick is found: the pick finder sees a whole stretch and keeps only
   real peaks (find_picks).
2. Note-anchored timing: each take's attack lands exactly at its own time,
   early or late around the grid. The jump to the new timing ends just before
   the attack, so the attack itself is never crossfaded.
3. New fine detail on the copies: each overtone drifts by its own small
   detune (phase_drift), so two takes in one speaker cancel at random,
   changing frequencies like real takes do, not at regular ones (no flanger).

This file is a research reference. It processes a whole file, but every step
only needs a bounded look-ahead: find_picks about 0.3 s (its running median),
the timing LOOKAHEAD_MS, phase_drift one FFT frame.
"""
from dataclasses import dataclass, replace

import numpy as np

from tp_double import BLOCK, ONSET_FADE, DoubleParams, Doubler, Roll, Take, layout, onepole_lp

LOOKAHEAD_MS = 50.0      # the grid sits this far back; a take may be up to this early (40 ms spread + margin)
MARGIN_MS = 4.0          # a timing jump ends this long before a found pick (picks are found up to 2.7 ms late)
NEAR_MS = 2.0            # a jump may land this far from its exact timing if the waveform lines up there
NEAR_MATCH = 0.9         # ... and the match is at least this good; else it jumps to the exact timing
PICK_HOP = 64
PICK_HP = 1500.0
PICK_DELTA = 2.5         # a pick stands this far above the running median of the onset curve
PICK_WIN_MS = 25.0       # and is the highest within this distance
PICK_MED_MS = 300.0
DRIFT_HZ = 1.0           # each overtone of a copy drifts by about this detune
DRIFT_SMOOTH = 6         # bins of 23 Hz: one overtone moves as one piece
DRIFT_LO_HZ = 150.0      # nothing drifts below this; the low end stays tight
DRIFT_N = 2048
DRIFT_HOP = 256
BURST_CENTS = 15.0       # at each attack, each overtone starts this far off (random), like a plucked string
BURST_MS = 40.0          # ... and settles over about this long


def find_picks(x, fs):
    """Two onset curves, each divided by its own running median and summed:
    the rise of the level above PICK_HP in dB (the pick noise), and spectral
    flux of the log spectrum (a new note). A pick is a peak of the sum that is
    the highest within PICK_WIN_MS and above median + PICK_DELTA."""
    hop = PICK_HOP
    h = x - onepole_lp(x, PICK_HP, fs)
    h = h - onepole_lp(h, PICK_HP, fs)
    nfr = len(x) // hop
    le = 10.0 * np.log10(np.mean(h[: nfr * hop].reshape(nfr, hop) ** 2, axis=1) + 1e-10)
    back = int(0.020 * fs / hop)
    rise = np.array([max(0.0, le[i] - le[max(0, i - back): i].min()) if i else 0.0 for i in range(nfr)])
    nfft = 1024
    w = np.hanning(nfft)
    xp = np.concatenate((np.zeros(nfft), x))
    flux = np.zeros(nfr)
    prev = None
    for i in range(nfr):
        m = np.log1p(100.0 * np.abs(np.fft.rfft(w * xp[i * hop + hop: i * hop + hop + nfft])))
        if prev is not None:
            flux[i] = np.sum(np.maximum(0.0, m - prev))
        prev = m
    kmed = int(PICK_MED_MS * 1e-3 * fs / hop)

    def running_median(c):
        return np.array([np.median(c[max(0, i - kmed): i + kmed + 1]) for i in range(nfr)])

    odf = rise / (running_median(rise) + 1e-12) + flux / (running_median(flux) + 1e-12)
    med = running_median(odf)
    k = int(PICK_WIN_MS * 1e-3 * fs / hop)
    return [i * hop for i in range(nfr)
            if odf[i] == odf[max(0, i - k): i + k + 1].max() and odf[i] > med[i] + PICK_DELTA]


def phase_drift(y, rng, fs, amount=1.0):
    """Each overtone gets its own slow phase drift (about amount x DRIFT_HZ
    detune): a random drift rate per bin, smooth over DRIFT_SMOOTH bins. STFT,
    Hann, 8x overlap. Gives new fine detail without changing level or pitch you
    can hear. amount scales the speed; it never mixes dry and drifted signals,
    because that mix would make a comb again."""
    nfft, hop = DRIFT_N, DRIFT_HOP
    w = np.hanning(nfft)
    k = nfft // 2 + 1
    f = np.fft.rfftfreq(nfft, 1.0 / fs)
    ker = np.hanning(2 * DRIFT_SMOOTH + 1)
    rate = np.convolve(rng.standard_normal(k), ker / ker.sum(), "same")
    rate = rate / (rate.std() + 1e-12) * 2.0 * np.pi * amount * DRIFT_HZ * hop / fs
    rate[f < DRIFT_LO_HZ] = 0.0
    phi = np.zeros(k)
    n = len(y)
    yp = np.concatenate((y, np.zeros(nfft)))
    out = np.zeros(n + nfft)
    norm = np.zeros(n + nfft)
    for i in range(0, n, hop):
        X = np.fft.rfft(w * yp[i: i + nfft])
        out[i: i + nfft] += w * np.fft.irfft(X * np.exp(1j * phi), nfft)
        norm[i: i + nfft] += w * w
        phi += rate
    return out[:n] / np.maximum(norm[:n], 1e-6)


def phase_drift_notes(y, starts, rng, fs, amount=1.0):
    """phase_drift, done right (user heard phaser and a left lean; tests showed
    smeared attacks on the copies and 1-2 dB lost level):

    - Each note is processed on its own and its drift starts at 0 just before
      the attack, so the attack passes untouched. A new drift field is drawn
      for every note (a new "pluck"). Notes are joined with a short linear
      crossfade that ends MARGIN_MS before the attack.
    - Phase locking: every bin turns by the drift of the overtone peak it
      belongs to, so an overtone stays whole (no level loss, no phasiness).
    - Attack detune: right after the attack each overtone is BURST_CENTS off
      (random per overtone), settling over BURST_MS, as a plucked string does.
      The attack instant is untouched, but short notes get new fine detail too
      (with the slow drift alone, a 0.1 s chug note barely changes).

    starts: output sample index of every attack in this take."""
    nfft, hop = DRIFT_N, DRIFT_HOP
    n = len(y)
    w = np.hanning(nfft)
    k = nfft // 2 + 1
    f = np.fft.rfftfreq(nfft, 1.0 / fs)
    ker = np.hanning(2 * DRIFT_SMOOTH + 1)
    ker /= ker.sum()
    fade = int(MARGIN_MS * 1e-3 * fs)
    edges = [0] + [max(0, s - 2 * fade) for s in starts] + [n]
    out = np.zeros(n)
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        if b <= a:
            continue
        gain = np.zeros(n)                               # this note's share, linear crossfades of `fade`
        gain[a: b] = 1.0
        if i > 0:
            gain[a: a + fade] = np.arange(1, fade + 1) / fade
        if i < len(edges) - 2:
            gain[b: b + fade] = 1.0 - np.arange(1, fade + 1) / fade
        lo, hi = max(0, a - nfft), min(n, b + fade + nfft)
        seg = (y * gain)[lo: hi]
        t0 = a + fade - lo                               # the drift starts here (0 before)
        rate = np.convolve(rng.standard_normal(k), ker, "same")
        rate = rate / (rate.std() + 1e-12) * 2.0 * np.pi * amount * DRIFT_HZ / fs   # rad per sample
        rate[f < DRIFT_LO_HZ] = 0.0
        cents = np.convolve(rng.standard_normal(k), ker, "same")
        cents = cents / (cents.std() + 1e-12) * amount * BURST_CENTS
        cents[f < DRIFT_LO_HZ] = 0.0
        tau = BURST_MS * 1e-3 * fs
        burst = 2.0 * np.pi * f / fs * (2.0 ** (cents / 1200.0) - 1.0) * tau   # final phase of the burst, rad
        m = len(seg)
        sp = np.concatenate((np.zeros(nfft), seg, np.zeros(nfft)))
        acc = np.zeros(m + 3 * nfft)
        norm = np.zeros(m + 3 * nfft)
        for j in range(0, m + nfft, hop):
            X = np.fft.rfft(w * sp[j: j + nfft])
            centre = j + nfft // 2 - nfft                # in segment samples
            age = max(0, centre - t0)
            if age > 0:
                mag = np.abs(X)
                thr = mag.max() * 1e-3
                pk = np.nonzero((mag[2:-2] >= np.maximum.reduce([mag[:-4], mag[1:-3], mag[3:-1], mag[4:]]))
                                & (mag[2:-2] > thr))[0] + 2
                if len(pk):
                    mids = 0.5 * (pk[1:] + pk[:-1])
                    owner = pk[np.searchsorted(mids, np.arange(k))]
                    X = X * np.exp(1j * (rate[owner] * age + burst[owner] * (1.0 - np.exp(-age / tau))))
            acc[j: j + nfft] += w * np.fft.irfft(X, nfft)
            norm[j: j + nfft] += w * w
        z = acc[nfft: nfft + m] / np.maximum(norm[nfft: nfft + m], 1e-6)
        out[lo: hi] += z
    return out


def attack_times(take, n):
    """Output sample at which each pick of take.notes reaches its read head."""
    pos = np.arange(n) - take.d_log
    return [int(np.argmax(pos >= w)) for w, _, _ in take.notes if pos[-1] >= w]


class StudioTake(Take):
    """A take that knows the picks ahead of time. At every pick it jumps to its
    new timing so that the jump ends MARGIN_MS before the attack reaches the
    read head. Timings are spread on both sides of the grid (LOOKAHEAD_MS)."""

    def __init__(self, p, dp, capacity, rng, picks):
        fs = p.fs
        self.grid = LOOKAHEAD_MS * 1e-3 * fs     # set first: Take.__init__ calls _draw_delay
        super().__init__(p, dp, capacity, rng)
        self.margin = MARGIN_MS * 1e-3 * fs
        self.near = NEAR_MS * 1e-3 * fs
        self.picks = list(picks)
        self.pi = 0
        self.target = self._draw_delay()
        self.d = self.target
        self.planned = self._draw_delay() if self.picks else self.target
        self.next_moment = float("inf")          # no timing moves between picks: every pick is found

    def _draw_delay(self):
        tau = 0.5 * self.spread * self.timing.next()
        return self.grid + float(np.clip(tau, -self.spread, self.spread))

    def _due(self):
        """Output time at which the jump for the next pick must start."""
        P = self.picks[self.pi]
        return P + min(self.d, self.planned) - self.margin - ONSET_FADE

    def _jump_near(self, widx):
        """Jump to the planned timing. If the waveform lines up well within
        NEAR_MS of it, land there (a seamless splice); else land exactly."""
        self.target = self.planned
        if not self._splice_toward(widx, self.near, 0) or abs(self.d - self.target) > self.near:
            if self.fade_left == 0:
                self._jump_to(self.target, ONSET_FADE)

    def process(self, blk, onset=False):
        n = len(blk)
        b0 = self.w
        if self.pi < len(self.picks) and b0 + n > self._due() and self.fade_left == 0:
            self.buf[self.PAD + b0: self.PAD + b0 + n] = blk
            dp = self.dp
            self._jump_near(b0)
            self.cents = 0.5 * dp.pitch_cents * self.pitch.next()
            level = 10.0 ** (0.5 * dp.level_db * np.clip(self.rng.standard_normal(), -2, 2) / 20.0)
            tone = 10.0 ** (2.0 * dp.tone * np.clip(self.rng.standard_normal(), -2, 2) / 20.0)
            self.notes.append((self.picks[self.pi], level, tone))
            self.pi += 1
            self.planned = self._draw_delay()
        return super().process(blk, False)


@dataclass
class StudioParams(DoubleParams):
    decorr: float = 0.0          # the velvet filter is not needed: phase_drift replaces it
    drift: float = 1.0           # 0 ... 3, speed of the overtone drift on the copies (1 = about 1 Hz)


class StudioDoubler(Doubler):
    def __init__(self, p, dp):
        super().__init__(p, dp)
        self.latency = int(round(LOOKAHEAD_MS * 1e-3 * p.fs))   # plus one DRIFT_N frame in real time

    def process(self, x):
        p, dp = self.p, self.dp
        fs = p.fs
        x = x[:, None] if x.ndim == 1 else x
        n = len(x)
        left, right = x[:, 0], x[:, -1]
        mid = 0.5 * (left + right)
        picks = find_picks(mid, fs)
        pans = layout(dp.takes, dp.width)
        rng = np.random.default_rng(dp.seed)
        out = np.zeros((n, 2))
        delays = []
        norm = np.sqrt(2.0 / dp.takes)
        timing_only = replace(dp, pitch_cents=0.0, wander_cents=0.0)
        self.take_signals = []                                # each take before panning ("take per track")
        sources = getattr(self, "sources", None)              # own source per take (tp_double_resynth)
        for t, pan in enumerate(pans):
            src = sources[t] if sources else left if pan < 0 else right if pan > 0 else mid
            take = StudioTake(p, timing_only if t == 0 else dp, n,
                              np.random.default_rng(rng.integers(1 << 62)), picks)
            take.d_log = np.empty(n)
            y = np.empty(n)
            for b in range(0, n, BLOCK):
                y[b: b + BLOCK] = take.process(src[b: b + BLOCK])
            delays.append(take.d_log)
            if t == 0:                                        # the original: timing only
                gain = norm
            else:
                y = self._colour(y, take, np.random.default_rng(rng.integers(1 << 62)))
                if dp.drift > 0.0:
                    y = phase_drift_notes(y, attack_times(take, n),
                                          np.random.default_rng(rng.integers(1 << 62)), fs, dp.drift)
                gain = norm * 10.0 ** (dp.copies_db / 20.0)
            self.take_signals.append(gain / norm * y)
            a = 0.25 * np.pi * (pan + 1.0)
            out[:, 0] += gain * np.cos(a) * y
            out[:, 1] += gain * np.sin(a) * y
        self.picks = picks
        return out, delays
