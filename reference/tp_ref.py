"""Reference implementation of the Live engine (PLAN.md section 5).

Slow, offline, NumPy only. It is the spec for the C++ port: same math, same
order of steps. Every step is causal: the work done for input sample e uses
input samples <= e only.

Engines:
  Predictive()             THE CHOSEN LIVE ENGINE: predicted sines + varispeed (5.6)
  engine_a()               varispeed + onset re-sync, no STFT          (5.2)
  Hybrid(mode="tonal")     low-delay peak-locked phase vocoder only    (5.3) REJECTED
  Hybrid(mode="adaptive")  tonal mask + hand-over                      (5.4) REJECTED
  Hybrid(mode="residual")  STFT pass-through into the varispeed (test)
  Hybrid(mode="fixed")     same mask value for every peak (test)

The Hybrid class is kept because its tests prove the hand-over formula and
because its lessons matter for Studio mode (PLAN 5.7). Do not port it for Live.
"""
from dataclasses import dataclass

import numpy as np

TWO_PI = 2.0 * np.pi


def princarg(x):
    return (x + np.pi) % TWO_PI - np.pi


@dataclass
class Params:
    fs: float = 48000.0
    # low-delay STFT
    N: int = 4096            # frame length (look-back)
    S: int = 128             # synthesis length (output delay is S - 1)
    H: int = 32              # hop
    fall_pow: float = 2.0    # shape of the short falling edge of the analysis window (2 = half Hann)
    # varispeed
    d_min: int = 12          # smallest delay the interpolator allows
    d_max: int = 960         # forced splice above this (down-shift)
    r_up: int = 240          # runway for up-shifts
    rest_a: int = 96         # rest delay of engine A alone (it has no look-ahead)
    onset_fade: int = 48
    splice_fade: int = 192
    corr_len: int = 480
    search: int = 1200
    min_jump: int = 240
    idle_tol: int = 96
    onset_pre: int = 96      # hybrid: re-sync this many samples before the onset
    # peaks
    max_peaks: int = 150
    peak_floor: float = 1e-4     # amplitude, about -80 dBFS
    peak_rel_db: float = 70.0
    min_freq: float = 30.0
    match_bins: float = 1.5
    max_missed: int = 8
    # predictive engine: measuring window (no effect on latency)
    pred_n: int = 8192
    pred_fall: int = 2048
    pred_phase_tol: float = 4.0      # allowed phase error (rad) from a drifting frequency
    fit_hops: int = 12               # the fit gate looks at this many hops (8 ms)
    fit_lo: float = 0.35             # prediction explains less than this share: fully off
    fit_hi: float = 0.75             # more than this: fully on
    # mirror-image split (PLAN 5.7)
    split_max: int = 8               # look back up to this many hops
    split_below_hz: float = 3000.0   # only regions below this need the split
    # mask
    hist_len: int = 9
    hist_stride: int = 4
    vert_half: int = 8
    beta_lo: float = 0.6
    beta_hi: float = 0.8
    mask_rise: float = 0.010
    mask_fall: float = 0.003


# --------------------------------------------------------------------------
# Onset detector (PLAN 5.2). Power in a fast window against a slow window.
# --------------------------------------------------------------------------
def detect_onsets(x, fs):
    a_f = 1.0 - np.exp(-1.0 / (fs * 0.001))
    a_s = 1.0 - np.exp(-1.0 / (fs * 0.030))
    refractory = int(0.025 * fs)
    fast = slow = 0.0
    hold = 0
    out = []
    for n, v in enumerate(x.tolist()):
        pw = v * v
        fast += a_f * (pw - fast)
        if hold > 0:
            hold -= 1
        elif fast > 6.0 * slow and fast > 1e-5:
            out.append(n)
            hold = refractory
        slow += a_s * (pw - slow)
    return out


# --------------------------------------------------------------------------
# Varispeed delay line (PLAN 5.2)
# --------------------------------------------------------------------------
class Varispeed:
    TAPS = 16
    PHASES = 64
    PAD = 8192

    def __init__(self, p, ratio, rest, capacity):
        self.p = p
        self.r = ratio
        self.rest = float(rest)
        self.buf = np.zeros(self.PAD + capacity + 64)
        self.w = 0                      # samples written so far
        self.d = self.rest              # delay of the main read head
        self.d_old = 0.0
        self.fade_left = 0
        self.fade_len = 1
        self.fade_eq = True
        self.jump_count = 0
        self.d_log = None               # optional array: delay used for every sample (offline engine)
        self.dmax_eff = float(p.d_max)
        self.offsets = np.arange(-(self.TAPS // 2 - 1), self.TAPS // 2 + 1)
        fr = np.arange(self.PHASES + 1) / self.PHASES
        u = self.offsets[None, :] - fr[:, None]
        win = np.i0(8.0 * np.sqrt(np.clip(1.0 - (u / (self.TAPS / 2)) ** 2, 0.0, 1.0))) / np.i0(8.0)
        tab = np.sinc(u) * win
        self.table = tab / tab.sum(axis=1, keepdims=True)

    def _read(self, pos):
        ip = np.floor(pos).astype(np.int64)
        fp = (pos - ip) * self.PHASES
        pi = fp.astype(np.int64)
        a = (fp - pi)[:, None]
        wts = self.table[pi] * (1.0 - a) + self.table[pi + 1] * a
        return np.sum(self.buf[ip[:, None] + self.offsets[None, :]] * wts, axis=1)

    def _jump_to(self, target, fade, eq=True):
        if abs(self.d - target) < 4.0:
            return
        self.d_old = self.d
        self.d = float(target)
        self.fade_len = self.fade_left = fade
        self.fade_eq = eq
        self.jump_count += 1

    def _forced_splice(self, widx):
        p = self.p
        di = int(round(self.d))
        if self.r < 1.0:
            lo, hi = p.d_min, min(p.d_min + p.search, di - p.min_jump)
        else:
            lo = int(self.rest)
            hi = lo + p.search
        if hi <= lo:
            self._jump_to(self.rest, p.onset_fade)
            return
        base = self.PAD + widx
        lc = p.corr_len
        # compare the signal just before the read point with the signal just
        # before each candidate read point (the past only)
        ref = self.buf[base - di - lc: base - di]
        strip = self.buf[base - hi - lc: base - lo]
        num = np.correlate(strip, ref, "valid")          # index j <-> d' = hi - j
        cs = np.concatenate(([0.0], np.cumsum(strip * strip)))
        e_c = cs[lc:] - cs[:-lc]
        c = num / np.sqrt(np.dot(ref, ref) * e_c + 1e-20)
        # only true peaks of the match curve count; a point on the slope of a
        # peak would shift the phase a little at every splice (a pitch error)
        is_max = np.concatenate(([True], (c[1:-1] >= c[:-2]) & (c[1:-1] >= c[2:]), [True]))
        good = np.nonzero(is_max & (c >= c.max() - 0.02))[0]
        j = good[-1]                                     # smallest d' among the good ones
        frac = 0.0
        if 0 < j < len(c) - 1:                           # sub-sample position of the peak
            curve = c[j - 1] - 2.0 * c[j] + c[j + 1]
            if curve < 0.0:
                frac = 0.5 * (c[j - 1] - c[j + 1]) / curve
        self.d_old = self.d
        self.d = self.d - (di - (hi - (j + frac)))       # keeps the fractional part
        self.fade_len = self.fade_left = p.splice_fade
        self.fade_eq = bool(c[j] < 0.5)
        self.jump_count += 1

    def process(self, x, onsets=(), idle=False):
        """Feed a block. `onsets` are block-local sample indices for re-sync."""
        p = self.p
        n = len(x)
        b0 = self.w
        self.buf[self.PAD + b0: self.PAD + b0 + n] = x
        y = np.empty(n)
        step = 1.0 - self.r
        onsets = sorted(onsets)
        i = 0
        while i < n:
            if onsets and onsets[0] <= i:
                onsets.pop(0)
                self._jump_to(self.rest, p.onset_fade)
            elif self.fade_left == 0:
                if step > 0 and self.d > self.dmax_eff:
                    self._forced_splice(b0 + i)
                elif step < 0 and self.d < p.d_min:
                    self._forced_splice(b0 + i)
                elif idle and abs(self.d - self.rest) > p.idle_tol:
                    self._jump_to(self.rest, p.onset_fade)
            seg = n - i
            if onsets:
                seg = min(seg, onsets[0] - i)
            if self.fade_left > 0:
                seg = min(seg, self.fade_left)
            elif step > 0:
                seg = min(seg, int(np.ceil((self.dmax_eff - self.d) / step)) + 1)
            elif step < 0:
                seg = min(seg, int(np.ceil((self.d - p.d_min) / -step)) + 1)
            seg = max(seg, 1)
            k = np.arange(seg)
            wpos = self.PAD + b0 + i + k
            out = self._read(wpos - (self.d + k * step))
            if self.d_log is not None:
                self.d_log[b0 + i: b0 + i + seg] = self.d + k * step
            if self.fade_left > 0:
                old = self._read(wpos - (self.d_old + k * step))
                g = (self.fade_len - self.fade_left + k + 1) / self.fade_len
                if self.fade_eq:
                    out = np.sin(0.5 * np.pi * g) * out + np.cos(0.5 * np.pi * g) * old
                else:
                    out = g * out + (1.0 - g) * old
                self.d_old += seg * step
                self.fade_left -= seg
            self.d += seg * step
            y[i: i + seg] = out
            i += seg
        self.w += n
        return y


def engine_a(x, p, semitones, block=32):
    """Engine A alone. Returns (y, latency)."""
    r = 2.0 ** (semitones / 12.0)
    rest = p.rest_a + (p.r_up if r > 1.0 else 0)
    vs = Varispeed(p, r, rest, len(x))
    onsets = detect_onsets(x, p.fs)
    y = np.empty(len(x))
    env = 0.0
    a_env = 1.0 - np.exp(-block / (p.fs * 0.005))
    oi = 0
    for b in range(0, len(x), block):
        blk = x[b: b + block]
        loc = []
        while oi < len(onsets) and onsets[oi] < b + len(blk):
            loc.append(onsets[oi] - b)
            oi += 1
        env += a_env * (float(np.mean(blk * blk)) - env)
        y[b: b + len(blk)] = vs.process(blk, loc, idle=env < 1e-6)
    return y, rest


# --------------------------------------------------------------------------
# Low-delay STFT windows (PLAN 5.3.1)
# --------------------------------------------------------------------------
def make_windows(N, S, H, fall_pow=1.0):
    n = np.arange(N)
    L = N - S // 2
    a = np.empty(N)
    a[:L] = np.sin(0.5 * np.pi * n[:L] / L) ** 2          # long rise
    a[L:] = np.sin(np.pi * (n[L:] - (N - S)) / S) ** fall_pow   # short fall
    k = np.arange(S)
    prod = np.sin(np.pi * k / S) ** 2 * (2.0 * H / S)     # overlapped copies sum to 1
    s = prod / np.maximum(a[N - S:], 1e-9)
    n_c = N - (S + 1) / 2.0                               # centre of the output chunk
    return a, a * (n - n_c), s


# --------------------------------------------------------------------------
# Hybrid engine (PLAN 5.3 and 5.4)
# --------------------------------------------------------------------------
class Hybrid:
    def __init__(self, p, semitones, mode="adaptive", fixed_mask=0.5, first_order=True):
        self.p = p
        self.r = 2.0 ** (semitones / 12.0)
        self.mode = mode
        self.fixed_mask = fixed_mask
        self.first_order = first_order
        self.rest = p.d_min + (p.r_up if self.r > 1.0 else 0)
        self.debug = {}

    @property
    def latency(self):
        return self.p.S - 1 + (0 if self.mode == "tonal" else self.rest)

    def process(self, x):
        p, r, mode = self.p, self.r, self.mode
        N, S, H = p.N, p.S, p.H
        K = N // 2 + 1
        n_in = len(x)
        a, a_ramp, s_win = make_windows(N, S, H, p.fall_pow)
        amp_scale = 2.0 / a.sum()
        xp = np.concatenate((np.zeros(N), x))
        OFF = S                                           # array index = content time + OFF
        ola_t = np.zeros(n_in + N + 2 * S)
        ola_r = np.zeros(n_in + N + 2 * S)
        out_c = np.zeros(n_in + N + 2 * S)

        use_res = mode != "tonal"
        vs = Varispeed(p, r, self.rest, n_in + N) if use_res else None
        onset_at = [t - p.onset_pre for t in detect_onsets(x, p.fs)] if use_res else []
        oi = 0

        bins = np.arange(K)
        min_bin = int(np.ceil(p.min_freq * N / p.fs))
        tol = p.match_bins * TWO_PI / N
        a_up = 1.0 - np.exp(-H / (p.fs * p.mask_rise))
        a_dn = 1.0 - np.exp(-H / (p.fs * p.mask_fall))
        vert = np.arange(-p.vert_half, p.vert_half + 1)
        hist = np.zeros((p.hist_len, K))
        x_prev = np.zeros(K, dtype=complex)
        HL = p.split_max + 2                              # past frames kept for the mirror split
        xh = np.zeros((HL, K), dtype=complex)
        xth = np.zeros((HL, K), dtype=complex)
        split_m = np.arange(1, p.split_max + 1)
        om_split = TWO_PI * p.split_below_hz / p.fs
        # track state, sorted by frequency
        t_om = np.zeros(0)
        t_th = np.zeros(0)
        t_mk = np.zeros(0)
        t_ms = np.zeros(0, dtype=int)
        last_jump = 0
        res_env = ton_env = 0.0
        a_env = 1.0 - np.exp(-H / (p.fs * 0.005))
        mask_log = []

        for j in range(n_in // H):
            e = (j + 1) * H - 1                           # newest input sample of this frame
            frame = xp[e + 1: e + 1 + N]
            X = np.fft.rfft(frame * a)
            mag = np.abs(X) * amp_scale
            Yt = np.zeros(K, dtype=complex)
            Xr = X

            pk = np.zeros(0, dtype=int)
            if mode != "residual":
                thr = max(p.peak_floor, mag.max() * 10.0 ** (-p.peak_rel_db / 20.0))
                c = mag[2:-2]
                is_pk = (c > mag[1:-3]) & (c >= mag[3:-1]) & (c > mag[:-4]) & (c >= mag[4:]) & (c > thr)
                pk = np.nonzero(is_pk)[0] + 2
                pk = pk[pk >= min_bin]
                if len(pk) > p.max_peaks:
                    pk = np.sort(pk[np.argsort(mag[pk])[-p.max_peaks:]])

            if len(pk) > 0:
                P = len(pk)
                # regions: split at the lowest bin between neighbouring peaks
                lo = np.zeros(P, dtype=int)
                hi = np.full(P, K - 1, dtype=int)
                for q in range(P - 1):
                    v = pk[q] + 1 + int(np.argmin(mag[pk[q] + 1: pk[q + 1]]))
                    hi[q] = v - 1
                    lo[q + 1] = v
                # true frequency from the phase change since the last frame
                expect = TWO_PI * pk * H / N
                have_prev = np.abs(x_prev[pk]) > 1e-12
                dphi = np.angle(X[pk] * np.conj(x_prev[pk]))
                om = np.where(have_prev, (expect + princarg(dphi - expect)) / H, TWO_PI * pk / N)
                reg = np.repeat(np.arange(P), hi - lo + 1)

                # Split low regions into the tone (Pb) and its mirror image from
                # negative frequency (Qb). A steady tone seen D samples earlier is
                # P*exp(-j*om*D) + Q*exp(+j*om*D); with the frame now, P + Q, that
                # gives two equations for P and Q. (PLAN 5.7)
                Xt = np.fft.rfft(frame * a_ramp) if self.first_order else None
                m_k = 1 + np.argmax(np.abs(np.sin(om[:, None] * split_m[None, :] * H)), axis=1)
                d_k = m_k * H
                x_d = xh[(j - m_k) % HL, pk]              # this peak, D samples ago
                x_d1 = xh[(j - 1) % HL, pk]               # one hop ago
                x_d2 = xh[(j - 1 - m_k) % HL, pk]         # one hop and D ago
                floor = 0.5 * np.abs(X[pk])
                # near multiples of fs/(2H) every look-back is a whole number of
                # half periods and the two equations say the same thing: no split there
                well = np.abs(np.sin(om * d_k)) > 0.35
                low = (om < om_split) & (j - 1 - m_k >= 0) & well \
                    & (np.abs(x_d) > floor) & (np.abs(x_d1) > floor) & (np.abs(x_d2) > floor)
                # better frequency: phase change of the clean tone part, not of the mix
                for it in range(3):
                    ph_k = np.exp(1j * om * d_k)
                    den_k = 2j * np.sin(om * d_k)
                    p_now = (X[pk] * ph_k - x_d) / den_k
                    p_old = (x_d1 * ph_k - x_d2) / den_k
                    if it == 0:
                        # the split is only right for a steady tone; check that it looks like one
                        an, ao = np.abs(p_now), np.abs(p_old)
                        low &= (an > 1.0 * floor) & (an < 3.2 * floor) & (ao > 0.6 * an) & (ao < 1.6 * an)
                    dphi_p = np.angle(p_now * np.conj(p_old))
                    om = np.where(low, (expect + princarg(dphi_p - expect)) / H, om)
                low_b = low[reg]
                rows = (j - m_k[reg]) % HL
                ph_b = np.exp(1j * om[reg] * d_k[reg])
                den_b = np.where(low_b, 2j * np.sin(om[reg] * d_k[reg]), 1.0)
                Pb = np.where(low_b, (X * ph_b - xh[rows, bins]) / den_b, X)
                Qb = X - Pb
                if self.first_order:
                    Ptb = np.where(low_b, (Xt * ph_b - xth[rows, bins]) / den_b, Xt)
                    Qtb = Xt - Ptb

                # delay of the residual path at this frame's chunk centre
                d_c = (vs.d + (1.0 - r) * (S - 1) / 2.0) if use_res else 0.0
                th_new = -om * d_c
                mk0 = self.fixed_mask if mode == "fixed" else (1.0 if mode == "tonal" else 0.0)

                # inherit state from the nearest old track
                if len(t_om) > 0:
                    jj = np.searchsorted(t_om, om)
                    j1 = np.clip(jj, 0, len(t_om) - 1)
                    j0 = np.clip(jj - 1, 0, len(t_om) - 1)
                    pick = np.where(np.abs(t_om[j1] - om) < np.abs(t_om[j0] - om), j1, j0)
                    hit = np.abs(t_om[pick] - om) < tol
                    th = np.where(hit, t_th[pick] + (r - 1.0) * 0.5 * (t_om[pick] + om) * H, th_new)
                    mk = np.where(hit, t_mk[pick], mk0)
                    used = np.zeros(len(t_om), dtype=bool)
                    used[pick[hit]] = True
                else:
                    th = th_new.copy()
                    mk = np.full(P, mk0)
                    used = np.zeros(0, dtype=bool)

                # mask
                if mode != "adaptive":
                    mk = np.full(P, mk0)
                else:
                    ht = np.median(np.maximum(np.maximum(hist[:, pk - 1], hist[:, pk]), hist[:, pk + 1]), axis=0)
                    vf = np.median(mag[np.clip(pk[:, None] + vert[None, :], 0, K - 1)], axis=1)
                    rs = ht * ht / (ht * ht + vf * vf + 1e-30)
                    raw = np.sin(0.5 * np.pi * np.clip((rs - p.beta_lo) / (p.beta_hi - p.beta_lo), 0.0, 1.0)) ** 2
                    mk = mk + np.where(raw > mk, a_up, a_dn) * (raw - mk)

                # hand-over: after a jump of the residual path, peaks that are
                # still mostly in the residual path follow it
                if use_res and vs.jump_count != last_jump:
                    th = np.where(mk < 0.5, th_new, th)
                    last_jump = vs.jump_count
                th = princarg(th)

                # move each region
                delta = (r - 1.0) * om * N / TWO_PI
                sh = np.rint(delta).astype(int)
                eps = delta - sh
                rot = np.exp(1j * (th + np.pi * sh * (S + 1) / N))
                kq = TWO_PI * eps[reg] / N
                VP, VQ = Pb, Qb
                if self.first_order:
                    VP = Pb + 1j * kq * Ptb
                    VQ = Qb - 1j * kq * Qtb
                # the tone itself moves by +sh with rot; its mirror image moves
                # by -sh with the conjugate. Bins that cross zero fold back.
                Yt = np.zeros(K, dtype=complex)
                for vals, dst, first in ((mk[reg] * VP * rot[reg], bins + sh[reg], 0),
                                         (mk[reg] * VQ * np.conj(rot[reg]), bins - sh[reg], 1)):
                    vals = np.where(dst < 0, np.conj(vals), vals)
                    dst = np.abs(dst)
                    ok = (dst <= K - 2) & (bins >= first)     # bin 0 has no separate mirror part
                    Yt += np.bincount(dst[ok], weights=vals.real[ok], minlength=K) \
                        + 1j * np.bincount(dst[ok], weights=vals.imag[ok], minlength=K)
                Yt[0] = 2.0 * Yt[0].real                      # at zero the part and its mirror coincide
                Xr = (1.0 - mk[reg]) * X

                # keep unmatched old tracks alive for a few frames
                gh = ~used & (t_ms < p.max_missed) if len(t_om) > 0 else np.zeros(0, dtype=bool)
                n_om = np.concatenate((om, t_om[gh]))
                n_th = np.concatenate((th, princarg(t_th[gh] + (r - 1.0) * t_om[gh] * H)))
                n_mk = np.concatenate((mk, t_mk[gh] * 0.9))
                n_ms = np.concatenate((np.zeros(P, dtype=int), t_ms[gh] + 1))
                order = np.argsort(n_om)
                t_om, t_th, t_mk, t_ms = n_om[order], n_th[order], n_mk[order], n_ms[order]
                if mode == "adaptive" and j % 8 == 0:
                    mask_log.append((e, float(np.sum(mk * mag[pk] ** 2) / (np.sum(mag[pk] ** 2) + 1e-30))))
                if use_res:
                    moving = (mk > 0.2) & (mk < 0.8) & (mag[pk] > 3e-3)
                    vs.dmax_eff = p.d_max * (1.5 if bool(np.any(moving)) else 1.0)
            elif mode == "tonal":
                Yt = X                                    # nothing to track: pass through
                Xr = np.zeros(K, dtype=complex)

            if j % p.hist_stride == 0:
                hist[(j // p.hist_stride) % p.hist_len] = mag
            x_prev = X
            if mode != "residual":
                xh[j % HL] = X
                if self.first_order:
                    xth[j % HL] = Xt if len(pk) > 0 else np.fft.rfft(frame * a_ramp)

            # overlap-add the last S samples of each inverse transform
            c0 = e - S + 1 + OFF
            ola_t[c0: c0 + S] += np.fft.irfft(Yt, N)[N - S:] * s_win
            if use_res:
                ola_r[c0: c0 + S] += np.fft.irfft(Xr, N)[N - S:] * s_win
            ton = ola_t[c0: c0 + H]                       # these H samples are final now
            if use_res:
                res = ola_r[c0: c0 + H]
                tau0 = e - S + 1
                loc = []
                while oi < len(onset_at) and onset_at[oi] < tau0 + H:
                    loc.append(max(0, onset_at[oi] - tau0))
                    oi += 1
                res_env += a_env * (float(np.mean(res * res)) - res_env)
                ton_env += a_env * (float(np.mean(ton * ton)) - ton_env)
                idle = res_env < 1e-3 * ton_env or res_env < 1e-8
                out_c[c0: c0 + H] = ton + vs.process(res, loc, idle)
            else:
                out_c[c0: c0 + H] = ton

        self.debug = {"mask_log": mask_log, "jumps": vs.jump_count if use_res else 0}
        y = np.zeros(n_in)
        y[S - 1:] = out_c[OFF: OFF + n_in - (S - 1)]      # content time t leaves at call time t + S - 1
        return y


# --------------------------------------------------------------------------
# Predictive engine (PLAN 5.6): measure partials with a long window, predict
# them forward as sines, subtract the prediction, varispeed what is left.
# No audio passes through the spectrum, so the STFT adds no delay.
# --------------------------------------------------------------------------
class Predictive:
    PADF = 4                         # zero padding of the analysis FFT

    def __init__(self, p, semitones, mode="adaptive", an_fall=None, guard_bins=3.0, lookahead=False):
        # lookahead=True: the measuring window is centred on "now" (it sees
        # pred_n/2 samples of the future). Nothing has to be predicted. In real
        # time this costs pred_n/2 samples of latency; offline it is free. (PLAN 5.8)
        self.lookahead = lookahead
        self.p = p
        self.r = 2.0 ** (semitones / 12.0)
        self.mode = mode             # "adaptive" or "allmodel" (mask 1 for every peak)
        self.an_fall = an_fall or p.pred_fall
        self.guard_bins = guard_bins
        self.rest = p.rest_a + (p.r_up if self.r > 1.0 else 0)
        self.debug = {}

    @property
    def latency(self):
        return self.rest

    def process(self, x):
        p, r = self.p, self.r
        N, H, PF = p.pred_n, p.H, self.PADF
        N4 = N * PF
        K = N4 // 2 + 1
        n_in = len(x)
        # analysis window: long smooth rise, shorter smooth fall, zero at both ends
        n = np.arange(N)
        fall = N // 2 if self.lookahead else self.an_fall
        la = N // 2 if self.lookahead else 0              # future samples the window may see
        L = N - fall
        a = np.where(n < L, np.sin(0.5 * np.pi * n / L) ** 2,
                     np.cos(0.5 * np.pi * (n - L) / fall) ** 2)
        asum = a.sum()
        n0 = float(np.sum(n * a) / asum)                  # centre of the window
        lag = (N - 1 - la) - n0                           # how old the measurement is
        xp = np.concatenate((np.zeros(N), x, np.zeros(N)))
        model_o = np.zeros(n_in + 4 * H)                  # predicted tonal part, original pitch
        model_s = np.zeros(n_in + 4 * H)                  # the same partials, shifted
        tt = np.arange(1, 2 * H + 1)
        fade = np.concatenate((np.arange(1, H + 1) / H, 1.0 - np.arange(1, H + 1) / H))

        vs = Varispeed(p, r, self.rest, n_in)
        onsets = detect_onsets(x, p.fs)
        oi = 0
        min_bin = int(np.ceil(p.min_freq * N4 / p.fs))
        gw = int(round(self.guard_bins * PF))
        tol = p.match_bins * TWO_PI / N
        a_up = 1.0 - np.exp(-H / (p.fs * p.mask_rise))
        a_dn = 1.0 - np.exp(-H / (p.fs * p.mask_fall))
        tau_s = 0.020 * p.fs
        a_slow = 1.0 - np.exp(-H / tau_s)
        vert = np.arange(-p.vert_half * PF, p.vert_half * PF + 1)
        hist = np.zeros((p.hist_len, K))
        x_prev = np.zeros(K, dtype=complex)
        t_om = np.zeros(0)
        t_th = np.zeros(0)
        t_mk = np.zeros(0)
        t_sl = np.zeros(0)
        t_os = np.zeros(0)
        t_ms = np.zeros(0, dtype=int)
        last_jump = 0
        res_env = ton_env = 0.0
        a_env = 1.0 - np.exp(-H / (p.fs * 0.005))
        mask_log = []
        y = np.zeros(n_in)
        # fit gate: does the prediction still match the input? (catches muted strings)
        sxm = np.zeros(p.fit_hops)
        smm = np.zeros(p.fit_hops)
        g_old = g_new = 1.0
        ramp = np.arange(1, H + 1) / H

        for j in range(n_in // H):
            # 1. audio for this hop: the prediction for it was made in earlier hops
            b0 = j * H
            g = g_old + (g_new - g_old) * ramp
            res = x[b0: b0 + H] - g * model_o[b0: b0 + H]
            ton = g * model_s[b0: b0 + H]
            # share of the prediction that the input confirms, over the last few ms
            sxm[j % p.fit_hops] = float(np.dot(x[b0: b0 + H], model_o[b0: b0 + H]))
            smm[j % p.fit_hops] = float(np.dot(model_o[b0: b0 + H], model_o[b0: b0 + H]))
            g_old = g_new
            if smm.sum() > 1e-7 * H * p.fit_hops:
                fit = np.clip((sxm.sum() / smm.sum() - p.fit_lo) / (p.fit_hi - p.fit_lo), 0.0, 1.0)
                g_new = float(np.sin(0.5 * np.pi * fit) ** 2)
            else:
                g_new = 1.0
            loc = []
            while oi < len(onsets) and onsets[oi] < b0 + H:
                loc.append(max(0, onsets[oi] - b0))
                oi += 1
            res_env += a_env * (float(np.mean(res * res)) - res_env)
            ton_env += a_env * (float(np.mean(ton * ton)) - ton_env)
            idle = res_env < 1e-3 * ton_env or res_env < 1e-8
            y[b0: b0 + H] = ton + vs.process(res, loc, idle)

            # 2. measure the partials with everything heard so far
            e = b0 + H - 1
            frame = xp[e + 1 + la: e + 1 + la + N]
            X = np.fft.rfft(frame * a, N4)
            mag = np.abs(X) * 2.0 / asum
            thr = max(p.peak_floor, mag.max() * 10.0 ** (-p.peak_rel_db / 20.0))
            # a peak must be the largest value within guard_bins on each side;
            # this also rejects the side lobes of strong neighbours
            win = np.lib.stride_tricks.sliding_window_view(np.pad(mag, gw), 2 * gw + 1)
            pk = np.nonzero((mag >= win.max(axis=1)) & (mag > thr))[0]
            pk = pk[(pk >= min_bin) & (pk < K - gw - 1)]
            if len(pk) > p.max_peaks:
                pk = np.sort(pk[np.argsort(mag[pk])[-p.max_peaks:]])
            if len(pk) > 0:
                P = len(pk)
                expect = TWO_PI * pk * H / N4
                have_prev = np.abs(x_prev[pk]) > 1e-12
                dphi = np.angle(X[pk] * np.conj(x_prev[pk]))
                om = np.where(have_prev, (expect + princarg(dphi - expect)) / H, TWO_PI * pk / N4)
                # complex amplitude of the partial, phase referred to frame sample 0
                u = om * N4 / TWO_PI - pk
                c = X[pk] * np.exp(-1j * TWO_PI * u * n0 / N4) / asum
                ln_a = np.log(2.0 * np.abs(c) + 1e-12)

                th_new = -om * (vs.d + r - 1.0)           # same delay as the residual path, now
                mk0 = 1.0 if self.mode == "allmodel" else 0.0
                if len(t_om) > 0:
                    jj = np.searchsorted(t_om, om)
                    j1 = np.clip(jj, 0, len(t_om) - 1)
                    j0 = np.clip(jj - 1, 0, len(t_om) - 1)
                    pick = np.where(np.abs(t_om[j1] - om) < np.abs(t_om[j0] - om), j1, j0)
                    hit = np.abs(t_om[pick] - om) < tol
                    th = np.where(hit, t_th[pick] + (r - 1.0) * 0.5 * (t_om[pick] + om) * H, th_new)
                    mk = np.where(hit, t_mk[pick], mk0)
                    sl = np.where(hit, t_sl[pick], ln_a)
                    osl = np.where(hit, t_os[pick], om)
                    used = np.zeros(len(t_om), dtype=bool)
                    used[pick[hit]] = True
                else:
                    th, mk, sl, osl = th_new.copy(), np.full(P, mk0), ln_a.copy(), om.copy()
                    used = np.zeros(0, dtype=bool)

                # is the frequency steady? A drifting partial (vibrato, bend, a
                # re-picked string) cannot be predicted `lag` samples ahead.
                osl = osl + a_slow * (om - osl)
                ph_err = 0.5 * np.abs(om - osl) / tau_s * lag * lag
                steady = np.clip(1.0 - ph_err / p.pred_phase_tol, 0.0, 1.0)

                if self.mode == "allmodel":
                    mk = np.ones(P)
                else:
                    ht = np.median(np.maximum(np.maximum(hist[:, pk - PF], hist[:, pk]), hist[:, pk + PF]), axis=0)
                    vf = np.median(mag[np.clip(pk[:, None] + vert[None, :], 0, K - 1)], axis=1)
                    rs = ht * ht / (ht * ht + vf * vf + 1e-30)
                    raw = np.sin(0.5 * np.pi * np.clip((rs - p.beta_lo) / (p.beta_hi - p.beta_lo), 0.0, 1.0)) ** 2
                    raw = raw * steady
                    mk = mk + np.where(raw > mk, a_up, a_dn) * (raw - mk)
                if vs.jump_count != last_jump:
                    th = np.where(mk < 0.5, th_new, th)
                    last_jump = vs.jump_count
                th = princarg(th)

                # the measurement is `lag` samples old: follow the decay to now
                sl = sl + a_slow * (ln_a - sl)
                gain = np.exp(np.clip((ln_a - sl) * (lag / tau_s), -0.7, 0.2))
                amp = mk * 2.0 * np.abs(c) * gain
                ph_now = np.angle(c) + om * (N - 1 - la)  # phase at sample e
                mo = (amp[:, None] * np.cos(ph_now[:, None] + om[:, None] * tt[None, :])).sum(axis=0)
                ms = (amp[:, None] * np.cos((ph_now + th)[:, None] + r * om[:, None] * tt[None, :])).sum(axis=0)
                model_o[e + 1: e + 1 + 2 * H] += fade * mo
                model_s[e + 1: e + 1 + 2 * H] += fade * ms

                gh = ~used & (t_ms < p.max_missed) if len(t_om) > 0 else np.zeros(0, dtype=bool)
                n_om = np.concatenate((om, t_om[gh]))
                order = np.argsort(n_om)
                t_th = np.concatenate((th, princarg(t_th[gh] + (r - 1.0) * t_om[gh] * H)))[order]
                t_mk = np.concatenate((mk, t_mk[gh] * 0.9))[order]
                t_sl = np.concatenate((sl, t_sl[gh]))[order]
                t_os = np.concatenate((osl, t_os[gh]))[order]
                t_ms = np.concatenate((np.zeros(P, dtype=int), t_ms[gh] + 1))[order]
                t_om = n_om[order]
                if j % 8 == 0:
                    mask_log.append((e, float(np.sum(mk * mag[pk] ** 2) / (np.sum(mag[pk] ** 2) + 1e-30))))
                moving = (mk > 0.2) & (mk < 0.8) & (mag[pk] > 3e-3)
                vs.dmax_eff = p.d_max * (1.5 if bool(np.any(moving)) else 1.0)
            if j % p.hist_stride == 0:
                hist[(j // p.hist_stride) % p.hist_len] = mag
            x_prev = X

        self.debug = {"mask_log": mask_log, "jumps": vs.jump_count}
        return y
