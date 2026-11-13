"""Offline "Perfect" engine (PLAN.md section 5.8). Research code, not causal.

It sees the whole file, so nothing is predicted:

  1. _tracks   find the partials: long centred window, peaks linked into tracks.
  2. _fit      fit a complex level curve A(t) to every track, in rounds: fit one
               track against what is left of the audio, subtract it, go on.
               Fit windows never reach across a "cut" (a pick attack or a sudden
               stop), so sound before and after a cut is fitted separately. Where
               a partial just rings on through a cut, the cut is dropped again.
  3. _render   play every track at r times its frequency with its own level
               curve; send what is left (attacks, noise) through the varispeed.
               A track can hold two or three partials a few Hz apart (the window
               cannot split them); its level curve then beats. _shifted_curve
               splits such a curve into decaying sines (matrix pencil method) and
               slows each one's offset by r, so the beat slows down like on a
               really down-tuned guitar.

The output is `latency` samples late (the rest delay of the varispeed), like
the other engines, so the same test code can score it.
"""
import numpy as np

from tp_ref import TWO_PI, Varispeed, princarg


def detect_attacks(x, fs, win=512, hop=64, lag=4, half_s=0.1, factor=2.5):
    """Pick attacks by spectral flux: new energy showing up in any frequency band.
    This also finds a new pick while the note before it still rings, which a plain
    level detector misses. Not causal (the threshold looks both ways). Returns rough
    sample positions; pass them to attack_start()."""
    if len(x) < win + hop:
        return []
    w = np.hanning(win)
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop]
    mag = np.log1p(100.0 * np.abs(np.fft.rfft(frames * w, axis=1)))
    flux = np.zeros(len(mag))
    flux[lag:] = np.maximum(mag[lag:] - mag[:-lag], 0.0).mean(axis=1)
    half = int(half_s * fs / hop)                         # threshold from this long each side
    near = int(0.010 * fs / hop)                          # one attack per 10 ms at most
    floor = 0.03 * flux.max()
    out = []
    for f in range(len(flux)):
        a, b = max(0, f - half), min(len(flux), f + half + 1)
        if flux[f] < factor * np.median(flux[a:b]) + floor:
            continue
        if flux[f] < flux[max(0, f - near): f + near + 1].max():
            continue
        out.append(f * hop + win // 2 + hop)
    return out


def attack_start(x, t, back=300, ahead=200):
    """Exact start of an attack near t: the last moment before t where the level is
    still down at its lowest point (within 1 % of the way up to the peak that follows)."""
    a, b = max(0, t - back), min(len(x), t + ahead)
    env = np.convolve(x[a:b] ** 2, np.ones(48) / 48.0, mode="same")
    split = min(t - a, len(env) - 1)
    lowest = float(env[: split + 1].min())
    level = lowest + 0.01 * (float(env[split:].max()) - lowest)
    low = np.nonzero(env[: split + 1] <= level)[0]
    return max(0, a + int(low[-1]) - 24)                  # a little early is harmless, late is not


def detect_stops(x, fs):
    """Sudden ends (strings muted by hand): the power falls under 3 % of what it
    was 20 ms earlier. A natural decay is far slower than that."""
    # The power window (20 ms) must be longer than one period of the lowest note,
    # or the level of a ringing low string seems to jump up and down by itself.
    win, hop, back = int(0.020 * fs), int(0.005 * fs), 8
    cs = np.concatenate(([0.0], np.cumsum(x * x)))
    ends = np.arange(win, len(x), hop)
    pw = (cs[ends] - cs[ends - win]) / win
    out, hold = [], 0
    for i in range(back, len(ends)):
        if hold > 0:
            hold -= 1
        elif pw[i - back] > 1e-5 and pw[i] < 0.03 * pw[i - back]:
            # the stop lies between the two windows: the last moment the level was still up
            a = int(ends[i - back]) - win // 2
            env = np.convolve(x[a: ends[i]] ** 2, np.ones(64) / 64.0, mode="same")
            up = np.nonzero(env >= 0.1 * pw[i - back])[0]
            out.append(a + (int(up[-1]) + 1 if len(up) else 0))
            hold = 12
    return out


class Offline:
    PADF = 4                 # zero padding of the tracking FFT
    PAD = 8192               # silence added around the audio for the fit windows

    def __init__(self, p, semitones, n_an=8192, hop=128, rounds=5, mu=0.8, min_len=0.03,
                 win_periods=3.0, win_min=512, blend=48, join_after=2, join_tol=0.25, use_cuts=True,
                 split_beats=True, pencil_max=3, pencil_min_frames=24, pencil_fit=0.1, ring_on=True):
        self.p = p
        self.r = 2.0 ** (semitones / 12.0)
        self.n_an = n_an                 # tracking window (centred)
        self.hop = hop                   # frame spacing of tracks and level curves
        self.rounds = rounds
        self.mu = mu                     # step size of each fit update
        self.min_len = min_len           # shortest track kept (seconds)
        self.win_periods = win_periods   # fit window = this many periods of the gap to the nearest partial
        self.win_min = win_min
        self.blend = blend               # samples to cross over at a cut
        self.join_after = join_after     # after this many rounds, drop cuts a partial rings through
        self.join_tol = join_tol
        self.join_fit = 0.15                   # _join: model error above this means "something happened"
        self.min_mass = 0.1                    # a fit frame needs this share of its window inside its stretch
        self.use_births = False                # tried 2026-11-13, no gain yet (PLAN 5.8.4)
        self.birth_len = 4096                  # window on each side of a pick for _births
        self.birth_fall = 512                  # its short edge, at the pick
        self.birth_ratio = 0.1                 # silent before the pick: below this share of the level after
        self.use_cuts = use_cuts
        self.split_beats = split_beats
        self.pencil_max = pencil_max           # at most this many partials per track
        self.pencil_min_frames = pencil_min_frames
        self.pencil_fit = pencil_fit           # split only if the sines leave less than this (relative)
        self.ring_on = ring_on                 # at another string's pick, a ringing partial keeps its phase
        self.sync_lead = 192             # re-sync the varispeed this many samples before each attack
        # 40 samples of room, so a re-sync can aim below `rest` and drift up to it (see _render)
        self.rest = p.d_min + 40 + (p.r_up if self.r > 1.0 else 0)
        self.debug = {}

    @property
    def latency(self):
        return self.rest

    def process(self, x, true_attacks=None):
        """true_attacks: exact pick positions (samples), for diagnosis only. They replace
        the detector, to measure how much of the error comes from missed picks."""
        x = np.asarray(x, dtype=float)
        if true_attacks is not None:
            attacks = sorted(set(int(a) for a in true_attacks))
        else:
            attacks = sorted(set(attack_start(x, t) for t in detect_attacks(x, self.p.fs)))
        stops = detect_stops(x, self.p.fs)
        cuts = sorted(set(attacks + stops)) if self.use_cuts else []
        self.debug["attacks"], self.debug["stops"] = len(attacks), len(stops)
        tracks = self._tracks(x)
        for t in tracks:
            lo, hi = self._span(t, len(x))
            t["cuts"] = [c for c in cuts if lo < c < hi]
            t["cuts0"] = list(t["cuts"])
        if self.use_births:
            self._births(x, tracks, attacks)
        self.debug["born_late"] = sum(1 for t in tracks if t.get("birth") is not None
                                      and any(c < t["birth"] for c in t["cuts0"]))
        residual = self._fit(x, tracks)
        self._other = self._other_string_picks(tracks, attacks) if self.ring_on else set()
        self.debug["other_string_picks"] = len(self._other)
        return self._render(x, tracks, residual, attacks)

    def _births(self, x, tracks, attacks):
        """The pick at which each partial starts. The centred tracking window sees a partial
        up to 85 ms before it sounds, and in the short stretch between two fast picks the
        fit cannot tell it from its neighbours. So look at each pick with two long windows,
        one ending at the pick and one starting there: the partial was born at the last
        pick before which it was silent."""
        L, F = self.birth_len, self.birth_fall
        # Lopsided windows: a long rise (sharp in frequency) and a short fall at the pick end,
        # so the last few ms before the pick count strongly. `w` ends at the pick; the window
        # after the pick is its mirror image.
        n = np.arange(L)
        w = np.where(n < L - F, np.sin(0.5 * np.pi * n / (L - F)) ** 2,
                     np.cos(0.5 * np.pi * (n - (L - F)) / F) ** 2)
        xp = np.concatenate((np.zeros(L), x, np.zeros(L)))
        for t in tracks:
            cand = [c for c in t["cuts0"] if c in set(attacks)]
            birth = None
            for c in cand:
                pos = np.arange(c - L, c + L)
                om = np.interp(pos, t["tf"], t["om"])           # held flat outside the track
                ph = np.cumsum(om)
                z = xp[pos + L] * np.exp(-1j * ph)
                past, fut = abs(np.dot(z[:L], w)), abs(np.dot(z[L:], w[::-1]))
                if fut > 1e-9 and past < self.birth_ratio * fut:
                    birth = c
            t["birth"] = birth

    def _other_string_picks(self, tracks, attacks):
        """Picks of a string other than the ones that ring. Sign: new partials appear
        (silent before the pick, loud after it), and the partials that were sounding
        ring on rather than restart. A re-pick of the same string brings no new
        frequencies; its partials restart."""
        fs = self.p.fs
        out = set()
        for c in attacks:
            new = ring = restart = 0
            for t in tracks:
                if c not in t["cuts0"]:
                    continue
                A, tf = np.abs(t["A"]), t["tf"]
                before = A[(tf >= c - 0.040 * fs) & (tf < c - 0.003 * fs)]
                after = A[(tf >= c + 0.003 * fs) & (tf < c + 0.040 * fs)]
                if len(after) == 0 or after.max() < 0.05 * A.max():
                    continue
                b = before.max() if len(before) else 0.0
                if b < 0.1 * after.max():
                    new += 1
                elif c in t["cuts"]:
                    restart += 1
                else:
                    ring += 1
            if new >= 2 and new + ring >= restart:
                out.add(c)
        return out

    # ------------------------------------------------------------------ 1
    def _tracks(self, x):
        p, N, Ha, PF = self.p, self.n_an, self.hop, self.PADF
        N4 = N * PF
        K = N4 // 2 + 1
        w = np.sin(np.pi * np.arange(N) / N) ** 2
        asum = w.sum()
        xp = np.concatenate((np.zeros(N // 2), x, np.zeros(N // 2 + Ha)))
        n_frames = len(x) // Ha + 1
        min_bin = int(np.ceil(p.min_freq * N4 / p.fs))
        gw = int(round(3.0 * PF))
        tol = p.match_bins * TWO_PI / N
        max_miss = 3
        active, done, frame_peaks = [], [], []
        x_prev = None

        for f in range(n_frames):
            X = np.fft.rfft(xp[f * Ha: f * Ha + N] * w, N4)      # centred on sample f*Ha
            mag = np.abs(X) * 2.0 / asum
            thr = max(p.peak_floor, mag.max() * 10.0 ** (-p.peak_rel_db / 20.0))
            win = np.lib.stride_tricks.sliding_window_view(np.pad(mag, gw), 2 * gw + 1)
            pk = np.nonzero((mag >= win.max(axis=1)) & (mag > thr))[0]
            pk = pk[(pk >= min_bin) & (pk < K - gw - 1)]
            if len(pk) > p.max_peaks:
                pk = np.sort(pk[np.argsort(mag[pk])[-p.max_peaks:]])
            if x_prev is not None and len(pk):
                expect = TWO_PI * pk * Ha / N4
                dphi = np.angle(X[pk] * np.conj(x_prev[pk]))
                om = (expect + princarg(dphi - expect)) / Ha
            else:
                om = TWO_PI * pk / N4
            x_prev = X
            frame_peaks.append((om, mag[pk]))

            # link peaks to the nearest live track; each track takes one peak at most
            claimed = {}
            taken = np.zeros(len(pk), dtype=bool)
            if active and len(pk):
                last = np.array([t["last"] for t in active])
                order = np.argsort(last)
                ls = last[order]
                jj = np.searchsorted(ls, om)
                j1 = np.clip(jj, 0, len(ls) - 1)
                j0 = np.clip(jj - 1, 0, len(ls) - 1)
                pick = np.where(np.abs(ls[j1] - om) < np.abs(ls[j0] - om), j1, j0)
                dist = np.abs(ls[pick] - om)
                for i in np.argsort(dist):
                    if dist[i] >= tol:
                        break
                    ti = int(order[pick[i]])
                    if ti not in claimed:
                        claimed[ti] = int(i)
                        taken[i] = True
            still = []
            for ti, t in enumerate(active):
                if ti in claimed:
                    i = claimed[ti]
                    t["fr"].append(f)
                    t["om"].append(float(om[i]))
                    t["mag"].append(float(mag[pk[i]]))
                    t["last"] = float(om[i])
                    t["miss"] = 0
                else:
                    t["miss"] += 1
                (still if t["miss"] <= max_miss else done).append(t)
            active = still
            for i in np.nonzero(~taken)[0]:
                active.append({"fr": [f], "om": [float(om[i])], "mag": [float(mag[pk[i]])],
                               "last": float(om[i]), "miss": 0})
        done += active

        min_frames = int(self.min_len * p.fs / Ha)
        tracks = []
        for t in done:
            if len(t["fr"]) < min_frames or max(t["mag"]) < 3.0 * p.peak_floor:
                continue
            fr = np.arange(t["fr"][0], t["fr"][-1] + 1)           # fill skipped frames
            om = np.interp(fr, t["fr"], t["om"])
            mg = np.interp(fr, t["fr"], t["mag"])
            # Gap to the nearest other partial (or to this partial's own mirror image).
            # Peaks more than 30 dB down are ignored: they are mostly window side lobes.
            gaps = []
            for f, o, m in zip(fr[::4], om[::4], mg[::4]):
                fo, fm = frame_peaks[f]
                d = np.abs(fo - o)
                d = np.sort(d[(fm > 0.03 * m) & (d > 1e-12)])
                gaps.append(d[0] if len(d) else np.inf)
            gap = min(float(np.median(gaps)), 2.0 * float(np.median(om)))
            W = int(np.clip(self.win_periods * TWO_PI / gap, self.win_min, N)) // 2 * 2
            tracks.append({"fr": fr, "tf": fr * Ha, "om": om, "peak": max(t["mag"]), "W": W,
                           "A": np.zeros(len(fr), dtype=complex), "cuts": []})
        tracks.sort(key=lambda t: -t["peak"])
        return tracks

    # helpers shared by fit and render
    def _span(self, t, n):
        Ha, W = self.hop, t["W"]
        lo = max(-self.PAD, int(t["fr"][0]) * Ha - W // 2 - Ha)
        hi = min(n + self.PAD, int(t["fr"][-1]) * Ha + W // 2 + Ha)
        return lo, hi

    def _phase(self, t, lo, hi):
        return np.cumsum(np.interp(np.arange(lo, hi), t["tf"], t["om"]))

    def _envelope(self, t, vals, a0, a1):
        """Frame values -> one value per sample in [a0, a1). Each stretch between two
        cuts uses its own frames only; at a cut the curve crosses over in `blend` samples.
        The curve is zero one hop outside the track."""
        Ha, tf = self.hop, t["tf"]
        out = np.zeros(a1 - a0, dtype=complex)
        bounds = [a0] + [c for c in t["cuts"] if a0 < c < a1] + [a1]
        last = 0.0
        for s in range(len(bounds) - 1):
            b0, b1 = bounds[s], bounds[s + 1]
            sel = (tf >= b0) & (tf < b1)
            if sel.any():
                pos = np.arange(b0, b1)
                seg = np.interp(pos, tf[sel], vals[sel].real) + 1j * np.interp(pos, tf[sel], vals[sel].imag)
            else:
                seg = np.zeros(b1 - b0, dtype=complex)
            if s > 0:
                k = min(self.blend, len(seg))
                u = (np.arange(k) + 1.0) / (k + 1.0)
                seg[:k] = (1.0 - u) * last + u * seg[:k]
            out[b0 - a0: b1 - a0] = seg
            last = seg[-1]
        pos = np.arange(a0, a1)
        return out * np.clip((pos - (tf[0] - Ha)) / Ha, 0.0, 1.0) * np.clip((tf[-1] + Ha - pos) / Ha, 0.0, 1.0)

    # ------------------------------------------------------------------ 2
    def _fit(self, x, tracks):
        n, Ha, PAD = len(x), self.hop, self.PAD
        ep = np.concatenate((np.zeros(PAD), x, np.zeros(PAD)))    # what is left of the audio
        energy = [float(np.sum(x * x))]
        view = np.lib.stride_tricks.sliding_window_view
        joined = 0
        for rnd in range(self.rounds):
            for t in tracks:
                W, tf = t["W"], t["tf"]
                lo, hi = self._span(t, n)
                rot = np.exp(-1j * self._phase(t, lo, hi))
                ww = np.sin(np.pi * np.arange(W) / W) ** 2
                seg_audio = ep[PAD + lo: PAD + hi] * rot
                delta = -t["A"].copy()                             # frames with too little data go to zero
                bounds = [lo] + t["cuts"] + [hi]
                for s in range(len(bounds) - 1):
                    b0, b1 = bounds[s], bounds[s + 1]
                    fsel = np.nonzero((tf >= b0) & (tf < b1))[0]
                    if len(fsel) == 0:
                        continue
                    # only the audio between the two cuts counts for these frames
                    inside = np.zeros(hi - lo)
                    inside[b0 - lo: b1 - lo] = 1.0
                    starts = np.clip(tf[fsel] - W // 2 - lo, 0, hi - lo - W)
                    pv, gv = view(seg_audio * inside, W), view(inside, W)
                    for c in range(0, len(fsel), 64):
                        st = starts[c: c + 64]
                        z = pv[st] @ ww
                        mass = gv[st] @ ww
                        ok = mass > self.min_mass * ww.sum()
                        fi = fsel[c: c + 64]
                        # least squares for one frame: divide by the window weight that lies inside
                        delta[fi] = np.where(ok, self.mu * 2.0 * z / np.maximum(mass, 1e-9), delta[fi])
                if t.get("birth") is not None:
                    unborn = tf < t["birth"]
                    delta[unborn] = -t["A"][unborn]                 # silent before its own pick
                t["A"] = t["A"] + delta
                a0 = max(lo, int(tf[0]) - Ha)
                a1 = min(hi, int(tf[-1]) + Ha + 1)
                env = self._envelope(t, delta, a0, a1)
                ep[PAD + a0: PAD + a1] -= (env * np.conj(rot[a0 - lo: a1 - lo])).real
            energy.append(float(np.sum(ep[PAD: PAD + n] ** 2)))
            if rnd + 1 == self.join_after:
                joined = sum(self._join(t, ep) for t in tracks)
        self.debug["residual_db"] = [10.0 * np.log10(e / energy[0] + 1e-30) for e in energy]
        self.debug["tracks"] = len(tracks)
        self.debug["joined"] = joined
        return ep[PAD: PAD + n].copy()

    def _flat(self, t, idx):
        """The level curve at frames idx, measured against one fixed frequency instead of
        the tracked one (a beat makes the tracked frequency wobble). Sums of decaying sines
        stay sums of decaying sines this way."""
        tf, om = t["tf"], t["om"]
        track = np.concatenate(([0.0], np.cumsum(0.5 * (om[1:] + om[:-1]) * np.diff(tf))))
        om_bar = float(np.mean(om[idx]))
        dev = track[idx] - om_bar * (tf[idx] - tf[idx[0]])
        return t["A"][idx] * np.exp(1j * (dev - dev[0])), dev - dev[0]

    def _join(self, t, ep):
        """Keep a cut only where something happens to this partial. Test: do one or two
        undisturbed decaying sines explain its curve across the cut (+-60 ms)? If yes, it
        rings through (also through the dip of a beat with a close neighbour): drop the cut.
        If no, it restarts (a new pick, also of the same string at the same level, which
        changes the phase), stops, or gets a new partial added on top: keep the cut.
        Takes the old curve out of the residual and puts the new one in, so the fit can go on."""
        tf, A, fs = t["tf"], t["A"], self.p.fs
        span = int(0.060 * fs)
        keep = []
        for c in t["cuts"]:
            idx = np.nonzero((tf >= c - span) & (tf < c + span) & (np.abs(A) > 1e-9))[0]
            nb = int(np.sum(tf[idx] < c))
            if nb < 4 or len(idx) - nb < 4 or np.abs(A[idx[:nb]]).max() < 0.05 * np.abs(A[idx]).max():
                keep.append(c)                                     # starts here (or too little to tell)
                continue
            z = self._flat(t, idx)[0]
            err = min(self._pencil(z, m)[2] for m in (1, 2))
            if err >= self.join_fit:
                keep.append(c)
        if not self.use_cuts:
            keep = []
        dropped = len(t["cuts"]) - len(keep)
        if dropped:
            n = len(ep) - 2 * self.PAD
            lo, hi = self._span(t, n)
            a0 = max(lo, int(tf[0]) - self.hop)
            a1 = min(hi, int(tf[-1]) + self.hop + 1)
            rot = np.exp(-1j * self._phase(t, lo, hi))[a0 - lo: a1 - lo]
            old = self._envelope(t, A, a0, a1)
            t["cuts"] = keep
            new = self._envelope(t, A, a0, a1)
            ep[self.PAD + a0: self.PAD + a1] -= ((new - old) * np.conj(rot)).real
        return dropped

    # ------------------------------------------------------------------ 3
    @staticmethod
    def _pencil(z, order):
        """Fit z[k] = sum_m a_m * lam_m**k (matrix pencil method). Returns (lam, a, error)."""
        L = len(z)
        P = min(L // 2, 64)
        Y = np.lib.stride_tricks.sliding_window_view(z, P + 1)
        _, _, vh = np.linalg.svd(Y, full_matrices=False)
        V = vh[:order].T                       # rows of vh span the rows of Y: [1, lam, lam**2, ...]
        lam = np.linalg.eigvals(np.linalg.pinv(V[:-1]) @ V[1:])
        lam = lam / np.maximum(np.abs(lam), 1.0)               # a partial may not grow
        vand = lam[None, :] ** np.arange(L)[:, None]
        a = np.linalg.lstsq(vand, z, rcond=None)[0]
        err = np.linalg.norm(z - vand @ a) / (np.linalg.norm(z) + 1e-30)
        return lam, a, err

    def _shifted_curve(self, t):
        """Level curve for the shifted partial, one complex value per frame. Its phase
        changes are r times those of the measured curve (a frequency offset scales with
        the pitch). Where the curve is the sum of a few close partials, each one's offset
        is scaled on its own, so the beat between them slows down by r."""
        A, r = t["A"], self.r
        out = np.abs(A) * np.exp(1j * r * np.unwrap(np.angle(A)))
        t["split"] = 0
        if not self.split_beats:
            return out
        tf = t["tf"]
        # Phase of the frequency track at each frame. A beat also makes the tracked frequency
        # wobble, so the split works on the curve measured against a fixed frequency.
        track = np.concatenate(([0.0], np.cumsum(0.5 * (t["om"][1:] + t["om"][:-1]) * np.diff(tf))))
        bounds = [-np.inf] + t["cuts"] + [np.inf]
        for s in range(len(bounds) - 1):
            idx = np.nonzero((tf >= bounds[s]) & (tf < bounds[s + 1]) & (np.abs(A) > 1e-9))[0]
            if len(idx) < self.pencil_min_frames:
                continue
            om_bar = float(np.mean(t["om"][idx]))
            dev = track[idx] - om_bar * (tf[idx] - tf[idx[0]])
            dev -= dev[0]
            z = A[idx] * np.exp(1j * dev)
            lam1, a1, err1 = self._pencil(z, 1)
            if err1 < self.pencil_fit:
                continue                                        # one partial explains it
            best = None
            for m in range(2, self.pencil_max + 1):
                lam, a, err = self._pencil(z, m)
                if err < self.pencil_fit and err < 0.5 * err1:
                    best = (lam, a)
                    break
            if best is None:
                continue                                        # not a few decaying sines (vibrato...)
            lam, a = best
            lam_s = np.abs(lam) * np.exp(1j * r * np.angle(lam))
            zs = (lam_s[None, :] ** np.arange(len(idx))[:, None]) @ a
            zs *= np.exp(-1j * r * dev)                         # back to the (shifted) wobbling track
            # keep the phase the plain curve has at the first frame, so the pieces fit together
            zs *= np.exp(1j * (np.angle(out[idx[0]]) - np.angle(zs[0])))
            out[idx] = zs
            t["split"] += 1
        return out

    def _ring_on(self, t, env, env_sf, track, sig, sl, b0, b1, a0, c_prev):
        """At another string's pick, a partial that was already ringing is the sum of the
        old string (it rings on, undisturbed) and the new one on almost the same frequency.
        A real down-tuned guitar keeps each one's phase from its own pick, so the two drift
        apart by (1 - r) * omega * (time between the picks), which changes their sum.
        Old part: the curve from just before the pick, carried on with the measured decay,
        keeping the old phase reference. New part: what is left, referenced to this pick.
        Writes into sig[sl]; returns False if there is too little to work with."""
        r, Ha, tf, A = self.r, self.hop, t["tf"], t["A"]
        before = np.nonzero(tf < b0 - self.blend)[0]
        after = np.nonzero((tf >= b0 + self.blend) & (tf < b1))[0]
        if len(before) == 0 or len(after) < 4:
            return False
        j0 = before[-1]
        if abs(A[j0]) < 0.1 * np.abs(A[after]).max():
            return False                                           # nothing much was ringing
        lam = self._pencil(A[after], 1)[0][0]                       # decay and drift after the pick
        lam = lam / max(abs(lam), 1.0)
        if abs(lam) < 0.5:
            return False                                           # no steady decay to carry on
        pos = np.arange(b0, b1)
        kf = (pos - tf[j0]) / Ha
        step = np.exp(np.log(lam) * kf)
        old = A[j0] * step
        if np.abs(A[after]).min() < 0.5 * np.abs(A[j0] * np.exp(np.log(lam) * (tf[after] - tf[j0]) / Ha)).max():
            return False                                           # it did not ring on (muted or restarted)
        new = env[sl] - old
        # old part: continue the previous stretch's shifted phase at frame j0
        C = np.angle(env_sf[j0]) + c_prev - r * np.angle(A[j0])
        ph_old = r * track[sl] + r * (np.angle(A[j0]) + np.angle(lam) * kf) + C
        part = np.abs(old) * np.cos(ph_old)
        # new part: referenced to this pick, like any partial that starts at a pick
        psi_n = track[sl] + np.unwrap(np.angle(new))
        psi_ns = r * psi_n
        i1 = min(self.blend + 16, len(psi_n) - 9)
        om_o = (psi_n[i1 + 8] - psi_n[i1]) / 8.0
        c_new = (psi_n[i1] - om_o * i1) - (psi_ns[i1] - r * om_o * i1)
        sig[sl] = part + np.abs(new) * np.cos(psi_ns + c_new)
        t["ring_on"] = t.get("ring_on", 0) + 1
        return True

    def _render(self, x, tracks, residual, attacks):
        p, r, rest, Ha = self.p, self.r, self.rest, self.hop
        n = len(x)

        # residual through the varispeed. Offline, the re-sync can be placed just before each attack.
        vs = Varispeed(p, r, rest, n)
        vs.d_log = np.full(n, float(rest))
        # Early enough that the re-sync crossfade is over before the attack begins. The delay
        # drifts by (1 - r) per sample, so aim the re-sync a little off: then the delay is
        # exactly `rest` when the attack arrives, and the attack lines up with the tonal part.
        # Output index n plays residual[n - d(n)]. We want output index c + rest to play
        # residual[c] at an attack c, so d must be exactly `rest` there.
        sync = sorted(max(0, t - self.sync_lead) for t in attacks)
        aim = rest - (1.0 - r) * (self.sync_lead + rest)
        attacks = set(attacks)
        oi = 0
        y_res = np.empty(n)
        tonal = x - residual
        res_env = ton_env = 0.0
        a_env = 1.0 - np.exp(-32 / (p.fs * 0.005))
        for b in range(0, n, 32):
            blk = residual[b: b + 32]
            loc = []
            while oi < len(sync) and sync[oi] < b + len(blk):
                loc.append(sync[oi] - b)
                oi += 1
            res_env += a_env * (float(np.mean(blk * blk)) - res_env)
            ton_env += a_env * (float(np.mean(tonal[b: b + 32] ** 2)) - ton_env)
            vs.rest = aim if loc else float(rest)
            y_res[b: b + len(blk)] = vs.process(blk, loc, idle=res_env < 1e-3 * ton_env or res_env < 1e-8)
        vs.rest = float(rest)

        out = np.zeros(n + rest + 2 * self.PAD)
        for t in tracks:
            if np.abs(t["A"]).max() < 1e-6:
                continue
            tf = t["tf"]
            lo, hi = self._span(t, n)
            a0 = max(lo, int(tf[0]) - Ha)
            a1 = min(hi, int(tf[-1]) + Ha + 1)
            env = self._envelope(t, t["A"], a0, a1)
            env_sf = self._shifted_curve(t)
            env_s = self._envelope(t, env_sf, a0, a1)
            amp = np.abs(env)
            # total phase = frequency track + phase of the fitted curve (this carries vibrato detail)
            track = self._phase(t, lo, hi)[a0 - lo: a1 - lo]
            psi = track + np.unwrap(np.angle(env))
            psi_s = r * track + np.unwrap(np.angle(env_s))      # the same, shifted
            # Start phase of each stretch that begins at a pick attack: what the residual
            # path gives this partial at that moment, so both parts of the attack add up.
            # A partial that keeps most of its level through the attack rings on: its phase must not jump.
            starts = [a0]
            for c in t["cuts"]:
                if not (a0 + 8 < c < a1 - self.blend - 8 and c in attacks):
                    continue
                if amp[c - a0 - 4] < 0.5 * amp[c - a0 + self.blend + 4] or c in self._other:
                    starts.append(c)
            sig = np.zeros(a1 - a0)
            c = 0.0
            for s, b0 in enumerate(starts):
                b1 = starts[s + 1] if s + 1 < len(starts) else a1
                sl = slice(b0 - a0, b1 - a0)
                if s > 0 and b0 in self._other and self._ring_on(t, env, env_sf, track, sig, sl, b0, b1, a0, c):
                    continue                                           # done: old part and new part
                if s > 0 or b0 in attacks:
                    # Starts at a pick. Every partial of this pick uses the pick itself as the
                    # reference, where the residual path plays residual[b0] (d = rest there).
                    # The curve is not defined at the cut, so measure a little later and step
                    # back with the partial's own frequency.
                    i1 = min(b0 + self.blend + 16, b1 - 9) - a0
                    back = i1 - (b0 - a0)
                    om_o = (psi[i1 + 8] - psi[i1]) / 8.0
                    om_s = (psi_s[i1 + 8] - psi_s[i1]) / 8.0
                    c = (psi[i1] - om_o * back) - (psi_s[i1] - om_s * back)
                else:
                    # No pick at the start (the partial grows out of a ringing note): match the
                    # residual path where the partial gets loud.
                    loud = np.nonzero(amp[b0 - a0: b1 - a0] > 0.1 * amp[b0 - a0: b1 - a0].max())[0]
                    t0 = int(np.clip(b0 + (loud[0] if len(loud) else 0), max(a0, 0), min(a1, n) - 9))
                    te = t0 + rest
                    d0 = vs.d_log[te] if te < n else float(rest)
                    i0 = t0 - a0
                    om0 = (psi[i0 + 8] - psi[i0]) / 8.0
                    c = psi[i0] + om0 * (rest - d0) - psi_s[i0]
                sig[sl] = np.abs(env_s[sl]) * np.cos(psi_s[sl] + c)
            o0 = self.PAD + a0 + rest                              # the tonal part is `rest` late, like the residual
            out[o0: o0 + (a1 - a0)] += sig
        self.debug["split"] = sum(t.get("split", 0) for t in tracks)
        self.debug["jumps"] = vs.jump_count
        return out[self.PAD: self.PAD + n] + y_res
