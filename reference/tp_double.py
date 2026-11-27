"""Reference doubler (PLAN.md section 16). Slow, offline, NumPy only.

Makes 1-3 extra "takes" of an amped guitar. Each take is a varispeed delay
line: at every pick it draws a new timing and a new pitch for that note, like
a player recording the part again. Between picks it moves to a new timing
with matched splices. Each take also gets a level and tone change per pick.

Each copy also gets a velvet-noise filter above 600 Hz. It scrambles the
fine detail of the copy, so two takes in one speaker no longer cancel at
regular frequencies (a comb: it sounds like a flanger, worst in quad). It
halves the comb but raises the peaks about 2 times (PLAN 16.6).

The original is take 1. It is a take too, but with timing changes only (no
pitch, level or tone change), so no take is always first: the order of the
takes is mixed note by note, like real double tracks. Every take lands from
D_MIN (0.25 ms, what the interpolator needs) up to the timing spread after
the input. The plugin reports D_MIN as its latency: the fixed part that every
note has. The rest is the human timing itself, so Ableton must not remove it.

Every step is causal, like in tp_ref.py: the C++ port can follow it step by step.
"""
from dataclasses import dataclass, replace

import numpy as np

from tp_ref import Varispeed

BLOCK = 32               # samples per step; a new note starts at a block edge
ONSET_FADE = 64          # crossfade when a take jumps to its new timing at a pick
SPLICE_FADE = 192        # crossfade when a long note drifts too far and is spliced back
D_MIN = 12               # smallest delay the interpolator allows
BAND_MS = 5.0            # a note may drift this far from its timing before a splice
SEARCH_MS = 10.0         # a matched splice looks this far around the new timing
MOMENT_MS = 300.0        # between picks, a take moves to a new timing about this often
MATCH_MIN = 0.8          # a matched splice needs at least this much likeness, else it waits
PICK_HZ = 1500.0         # the pick detector listens above this
PICK_RATIO = 4.0         # pick = power above PICK_HZ jumps by this factor (6 dB)
TONE_HZ = 1500.0         # tone change = gain above this
DECORR_HZ = 600.0        # the velvet filter only works above this, the low end stays tight
VELVET_MS = 15.0         # length of the velvet filter
VELVET_PULSES = 30


@dataclass
class DoubleParams:
    """Plugin parameters (PLAN 16.3). Spreads are the largest offset; typical offsets are about half."""
    takes: int = 2               # 2, 3 or 4, the original included
    timing_ms: float = 8.0       # timing spread
    timing_jitter: float = 0.6   # 0 = same offset every note, 1 = new offset every note
    timing_drift: float = 0.3    # how fast the slow part moves (rushing / dragging)
    pitch_cents: float = 6.0     # pitch spread
    pitch_jitter: float = 0.6
    wander_cents: float = 1.0    # slow pitch movement inside a note
    level_db: float = 1.0        # level spread per note
    tone: float = 0.3            # 0 ... 1, tone change per note (up to +-4 dB above TONE_HZ)
    decorr: float = 1.0          # 0 ... 1, velvet filter on the copies (against the flanger sound)
    width: float = 1.0           # 0 ... 1
    copies_db: float = 0.0
    seed: int = 1


def layout(takes, width):
    """Pan of every take, -1 = left, +1 = right. Take 1 is the original."""
    w = width
    return {2: [-w, w], 3: [-w, w, 0.0], 4: [-w, w, -0.8 * w, 0.8 * w]}[takes]


class Roll:
    """One random number per note, made of a slow part (a random walk, so the
    player rushes or drags for a while) and a fresh part (new every note).
    The result has unit spread and is clipped to -2 ... 2."""

    def __init__(self, rng, jitter, drift):
        self.rng = rng
        self.j = float(np.clip(jitter, 0.0, 1.0))
        self.a = 0.995 - 0.6 * float(np.clip(drift, 0.0, 1.0))   # how much of the slow part is kept per note
        self.slow = rng.standard_normal()

    def next(self):
        self.slow = self.a * self.slow + np.sqrt(1.0 - self.a ** 2) * self.rng.standard_normal()
        v = np.sqrt(1.0 - self.j) * self.slow + np.sqrt(self.j) * self.rng.standard_normal()
        return float(np.clip(v, -2.0, 2.0))


def onepole_lp(x, hz, fs):
    a = 1.0 - np.exp(-2.0 * np.pi * hz / fs)
    y = np.empty(len(x))
    s = 0.0
    for n, v in enumerate(x.tolist()):
        s += a * (v - s)
        y[n] = s
    return y


def velvet(rng, amount, fs):
    """Velvet-noise filter: the first tap is the dry signal, then sparse random
    +-1 pulses that fade by 30 dB over VELVET_MS. amount = 0 gives a plain
    pass-through. Scaled to unit energy, so the level stays the same."""
    n = int(VELVET_MS * 1e-3 * fs)
    h = np.zeros(n)
    h[0] = 1.0
    grid = n / VELVET_PULSES
    for k in range(1, VELVET_PULSES):
        pos = int(k * grid + rng.uniform(0.0, grid - 1))
        h[pos] = amount * rng.choice((-1.0, 1.0)) * 10.0 ** (-1.5 * pos / n)
    return h / np.sqrt(np.sum(h * h))


def detect_picks(x, fs):
    """Clear picks only. Power above PICK_HZ in a 1 ms window against a 30 ms
    window. Distortion squashes the level jump of a pick in the full band, but
    the pick noise still stands out in the highs. Misses are fine: the take
    then keeps its timing until the next matched splice."""
    h = x - onepole_lp(x, PICK_HZ, fs)
    h = h - onepole_lp(h, PICK_HZ, fs)
    a_f = 1.0 - np.exp(-1.0 / (fs * 0.001))
    a_s = 1.0 - np.exp(-1.0 / (fs * 0.030))
    refractory = int(0.040 * fs)
    fast = slow = 0.0
    hold = 0
    out = []
    for n, v in enumerate(h.tolist()):
        pw = v * v
        fast += a_f * (pw - fast)
        if hold > 0:
            hold -= 1
        elif fast > PICK_RATIO * slow and fast > 1e-7:
            out.append(n)
            hold = refractory
        slow += a_s * (pw - slow)
    return out


class Take(Varispeed):
    """One made-up take. Uses the interpolator and the splice search of the
    transpose varispeed; the read speed changes per block instead of being fixed."""

    def __init__(self, p, dp, capacity, rng):
        super().__init__(p, 1.0, 0.0, capacity)
        fs = p.fs
        self.dp = dp
        self.rng = rng
        self.spread = dp.timing_ms * 1e-3 * fs
        self.band = BAND_MS * 1e-3 * fs
        self.timing = Roll(rng, dp.timing_jitter, dp.timing_drift)
        self.pitch = Roll(rng, dp.pitch_jitter, dp.timing_drift)
        self.target = self._draw_delay()
        self.d = self.target
        self.cents = 0.5 * dp.pitch_cents * self.pitch.next()
        self.wander = 0.0
        self.a_wander = 1.0 - np.exp(-BLOCK / (fs * 0.4))         # pitch wander moves over about 0.4 s
        self.search = SEARCH_MS * 1e-3 * fs
        self.moment = MOMENT_MS * 1e-3 * fs
        self.next_moment = self._draw_moment()
        self.notes = []          # per pick: (input index of the pick, level gain, tone gain)

    def _draw_delay(self):
        """A take cannot be earlier than D_MIN, so the timing is folded to the late side."""
        return D_MIN + min(abs(0.5 * self.spread * self.timing.next()), self.spread)

    def _draw_moment(self):
        return self.w + self.moment * self.rng.uniform(0.5, 1.5)

    def new_note(self, widx):
        """A clear pick: new timing, pitch, level and tone. The jump happens
        now, before the attack reaches this take's read head."""
        dp = self.dp
        self.target = self._draw_delay()
        self.cents = 0.5 * dp.pitch_cents * self.pitch.next()
        level = 10.0 ** (0.5 * dp.level_db * np.clip(self.rng.standard_normal(), -2, 2) / 20.0)
        tone = 10.0 ** (2.0 * dp.tone * np.clip(self.rng.standard_normal(), -2, 2) / 20.0)
        self.notes.append((widx, level, tone))
        self.next_moment = self._draw_moment()
        if self.fade_left == 0:
            self._jump_to(self.target, ONSET_FADE)

    def new_moment(self, widx):
        """Between picks: new timing and pitch, reached with a matched splice.
        If no good match is found the take keeps its timing and tries again."""
        old = self.target
        self.target = self._draw_delay()
        if abs(self.d - self.target) >= 24 and not self._splice_toward(widx, self.search, 24):
            self.target = old
            return
        self.cents = 0.5 * self.dp.pitch_cents * self.pitch.next()

    def _splice_toward(self, widx, reach, min_jump):
        """Jump by a whole number of waveform periods (best match of the recent
        past), as close to self.target as the match allows. Returns False if
        nothing matches well enough."""
        p = self.p
        di = int(round(self.d))
        lo = int(max(D_MIN, self.target - reach))
        hi = int(self.target + reach)
        base = self.PAD + widx
        lc = p.corr_len
        if base - hi - lc < 0 or hi <= lo:
            return False
        ref = self.buf[base - di - lc: base - di]
        strip = self.buf[base - hi - lc: base - lo]
        num = np.correlate(strip, ref, "valid")              # index j <-> d' = hi - j
        cs = np.concatenate(([0.0], np.cumsum(strip * strip)))
        e_c = cs[lc:] - cs[:-lc]
        c = num / np.sqrt(np.dot(ref, ref) * e_c + 1e-20)
        cand = hi - np.arange(len(c))
        is_max = np.concatenate(([True], (c[1:-1] >= c[:-2]) & (c[1:-1] >= c[2:]), [True]))
        good = np.nonzero(is_max & (c >= max(c.max() - 0.05, MATCH_MIN)) & (np.abs(cand - di) >= min_jump))[0]
        if len(good) == 0:
            return False
        j = good[np.argmin(np.abs(cand[good] - self.target))]
        if abs(cand[j] - self.target) >= abs(di - self.target):   # the take is already closer
            return False
        frac = 0.0
        if 0 < j < len(c) - 1:
            curve = c[j - 1] - 2.0 * c[j] + c[j + 1]
            if curve < 0.0:
                frac = 0.5 * (c[j - 1] - c[j + 1]) / curve
        self.d_old = self.d
        self.d = self.d - (di - (hi - (j + frac)))
        self.fade_len = self.fade_left = SPLICE_FADE
        self.fade_eq = bool(c[j] < 0.5)
        self.jump_count += 1
        return True

    def process(self, blk, onset):
        """Feed one block (len <= BLOCK). onset: a pick starts in this block."""
        n = len(blk)
        b0 = self.w
        self.buf[self.PAD + b0: self.PAD + b0 + n] = blk
        if onset:
            self.new_note(b0)
        elif self.fade_left == 0 and b0 >= self.next_moment:
            self.next_moment = self._draw_moment()
            self.new_moment(b0)
        elif self.fade_left == 0 and (abs(self.d - self.target) > self.band or self.d < D_MIN + 1):
            if not self._splice_toward(b0, self.band, int(0.5 * self.band)):
                self._jump_to(self.target, SPLICE_FADE, eq=True)
        self.wander += self.a_wander * (self.dp.wander_cents * self.rng.standard_normal() - self.wander)
        step = 1.0 - 2.0 ** ((self.cents + self.wander) / 1200.0)
        if self.d + n * step < D_MIN:          # never read the future
            step = (D_MIN - self.d) / n
        k = np.arange(n)
        wpos = self.PAD + b0 + k
        out = self._read(wpos - (self.d + k * step))
        self.d_log[b0: b0 + n] = self.d + k * step
        if self.fade_left > 0:
            m = min(n, self.fade_left)
            old = self._read(wpos[:m] - (self.d_old + k[:m] * step))
            g = (self.fade_len - self.fade_left + k[:m] + 1) / self.fade_len
            if self.fade_eq:
                out[:m] = np.sin(0.5 * np.pi * g) * out[:m] + np.cos(0.5 * np.pi * g) * old
            else:
                out[:m] = g * out[:m] + (1.0 - g) * old
            self.d_old += n * step
            self.fade_left -= m
        self.d += n * step
        self.w += n
        return out


class Doubler:
    def __init__(self, p, dp):
        self.p = p
        self.dp = dp
        self.latency = D_MIN

    def process(self, x):
        """x: (frames,) or (frames, 2). Returns (frames, 2) stereo and the per-take
        delays in samples (for the tests and the plugin's Takes view)."""
        p, dp = self.p, self.dp
        fs = p.fs
        x = x[:, None] if x.ndim == 1 else x
        n = len(x)
        left, right = x[:, 0], x[:, -1]
        mid = 0.5 * (left + right)
        onsets = set(o // BLOCK for o in detect_picks(mid, fs))
        pans = layout(dp.takes, dp.width)
        rng = np.random.default_rng(dp.seed)
        out = np.zeros((n, 2))
        delays = []
        norm = np.sqrt(2.0 / dp.takes)
        timing_only = replace(dp, pitch_cents=0.0, wander_cents=0.0)
        for t, pan in enumerate(pans):
            src = left if pan < 0 else right if pan > 0 else mid
            take = Take(p, timing_only if t == 0 else dp, n, np.random.default_rng(rng.integers(1 << 62)))
            take.d_log = np.empty(n)
            y = np.empty(n)
            for b in range(0, n, BLOCK):
                y[b: b + BLOCK] = take.process(src[b: b + BLOCK], b // BLOCK in onsets)
            delays.append(take.d_log)
            if t == 0:                                        # the original: timing only
                gain = norm
            else:
                y = self._colour(y, take, np.random.default_rng(rng.integers(1 << 62)))
                gain = norm * 10.0 ** (dp.copies_db / 20.0)
            a = 0.25 * np.pi * (pan + 1.0)                    # constant-power pan
            out[:, 0] += gain * np.cos(a) * y
            out[:, 1] += gain * np.sin(a) * y
        return out, delays

    def _colour(self, y, take, rng):
        """Level and tone per pick, then the velvet filter. The level change
        follows the read head: a note's level starts when its pick is heard in this take."""
        fs = self.p.fs
        n = len(y)
        if take.notes:
            picks = np.array([w for w, _, _ in take.notes])
            level = np.array([1.0] + [g for _, g, _ in take.notes])
            tone = np.array([1.0] + [g for _, _, g in take.notes])
            note = np.searchsorted(picks, np.arange(n) - take.d_log, side="right")
            level = onepole_lp(level[note], 300.0, fs)        # about 0.5 ms smoothing, no clicks
            tone = onepole_lp(tone[note], 300.0, fs)
            lo = onepole_lp(y, TONE_HZ, fs)
            y = level * (lo + tone * (y - lo))
        if self.dp.decorr > 0.0:
            lo = onepole_lp(onepole_lp(y, DECORR_HZ, fs), DECORR_HZ, fs)
            y = lo + np.convolve(y - lo, velvet(rng, self.dp.decorr, fs))[:n]
        return y


def fixed_doubler(x, p, delay_ms=12.0):
    """What a plain doubler does: the same signal, delayed, on the other side."""
    d = int(delay_ms * 1e-3 * p.fs)
    x = x if x.ndim == 1 else x.mean(axis=1)
    return np.stack((x, np.concatenate((np.zeros(d), x[: len(x) - d]))), axis=1)
