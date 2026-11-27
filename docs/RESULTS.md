# Results

## 2026-11-12 — Python reference prototype

Raw output of the full run: `docs/results_raw.txt`.
How to run it again: `cd reference` then `python run_tests.py all` (about 5 minutes).
`python run_tests.py` runs only engines A and M.

All signals are synthetic (the additive guitar model in `reference/synth.py`), 48 kHz.
No real guitar has been tested yet. Nobody has listened to anything yet.

### Engines

| Letter | Engine | Status |
|--------|--------|--------|
| A | Varispeed with onset re-sync (PLAN 5.2) | Works. Kept as the residual path. |
| B | Bin-moving low-delay phase vocoder (PLAN 5.3) | Rejected. |
| H | B plus tonal mask (PLAN 5.4) | Rejected. |
| M | Predictive: predicted sines + varispeed (PLAN 5.6) | Chosen for Live mode. |

### Basic checks (all pass)

| Check | Result |
|-------|--------|
| Low-delay STFT returns its input | error −300 dB |
| Reported latency = measured latency | A 96 = 96, B 127 = 127, H 139 = 139 samples |
| Sine 997 Hz, −1 semitone, side tones | A −93 dBc, B −95.5 dBc (with first-order fix; −78.6 without) |
| Sine pitch error | 0.00 cents for all |
| Hand-over: one tone split over both paths adds up | within 0.18 dB at 110 / 440 / 1000 / 3000 Hz, at −2, −5 and +2 semitones (gate was 0.5 dB) |

### Guitar scenarios

wobble = level wobble of steady partials that stand alone, mean / worst, in dB. Lower is better.
spec = distance to the perfect answer in dB. Lower is better.
dist = the same after a hard distortion stage.

| Scenario | A wobble | M wobble | A cents | M cents | A spec | M spec | A dist | M dist |
|----------|----------|----------|---------|---------|--------|--------|--------|--------|
| Single note E2, −2 | 0.02 / 0.04 | 0.04 / 0.09 | 0.35 | 0.03 | 0.30 | 0.28 | 1.78 | 2.31 |
| Power chord E5, −5 | 4.44 / 6.62 | 0.34 / 0.78 | 1.26 | 0.18 | 0.58 | 0.44 | 2.99 | 2.99 |
| Open E chord, −2 | 3.50 / 4.54 | 0.63 / 0.84 | 0.73 | 0.10 | 0.62 | 0.55 | 2.63 | 2.78 |
| Open E chord, −5 | 7.22 / 14.16 | 0.59 / 1.02 | 9.56 | 0.15 | 0.68 | 0.59 | 2.65 | 2.65 |
| Strum + late note, −2 | 3.72 / 4.82 | 1.59 / 7.68 | 1.71 | 0.46 | 0.74 | 0.80 | 4.02 | 4.35 |
| Chord stopped by hand, −2 | 3.93 / 5.19 | 0.46 / 0.70 | 1.91 | 0.16 | 0.51 | 0.50 | 2.15 | 2.74 |
| Single note E2, +2 | 0.03 / 0.08 | 0.04 / 0.12 | 0.27 | 0.00 | 0.63 | 0.26 | 2.65 | 2.31 |
| Open E chord, +2 | 0.38 / 1.43 | 0.44 / 1.28 | 0.40 | 0.03 | 0.79 | 0.77 | 3.37 | 3.26 |
| Palm mutes 200 bpm, −2 | – | – | – | – | 0.58 | 0.75 | 3.96 | 4.84 |
| Vibrato A3, −2 | – | – | – | – | 0.44 | 0.91 | 2.81 | 4.44 |

7-string scenarios (added 2026-11-12, same measures):

| Scenario | A wobble | M wobble | A cents | M cents | A spec | M spec | A dist | M dist |
|----------|----------|----------|---------|---------|--------|--------|--------|--------|
| Low B1 single note, −2 | 0.03 / 0.06 | 0.12 / 0.27 | 0.45 | 0.13 | 0.26 | 0.23 | 1.61 | 2.00 |
| B5 power chord (B1 + F#2), −2 | 2.76 / 4.54 | 0.59 / 1.45 | 2.26 | 0.33 | 0.45 | 0.36 | 2.50 | 2.48 |
| B5 power chord, −5 | – (no lone partials) | – | – | – | 0.50 | 0.41 | 2.80 | 2.63 |
| Drop A power chord (A1 + E2), −2 | 1.00 / 1.00 | 0.44 / 0.44 | 0.46 | 0.20 | 0.44 | 0.36 | 2.44 | 2.68 |

The low B works as well as the low E. No change to window sizes is needed for 7-string.

Attack latency (measured against the perfect answer) is the same for A and M:
2.2–3.1 ms for down-shifts, 6.2 ms for +2. Reported latency is 96 samples (2.0 ms) down, 336 samples (7.0 ms) up.

Engines B and H score 3–9 dB on "spec" and 2–9 dB on wobble in every scenario. See the raw file.

### Look-ahead experiment (2026-11-13, for the offline mode, PLAN 5.8)

Engine L = engine M with the measuring window centred on "now" (sees 85 ms of future). `python run_tests.py scen look`

| Scenario | A wobble | M wobble | L wobble | A spec | M spec | L spec |
|----------|----------|----------|----------|--------|--------|--------|
| Single note E2, −2 | 0.02 / 0.04 | 0.04 / 0.09 | 0.02 / 0.04 | 0.30 | 0.28 | 0.42 |
| Power chord E5, −5 | 4.44 / 6.62 | 0.34 / 0.78 | 0.07 / 0.30 | 0.58 | 0.44 | 0.50 |
| Open E chord, −2 | 3.50 / 4.54 | 0.63 / 0.84 | 0.22 / 0.55 | 0.62 | 0.55 | 0.61 |
| Open E chord, −5 | 7.22 / 14.16 | 0.59 / 1.02 | 0.26 / 0.75 | 0.68 | 0.59 | 0.55 |
| Strum + late note, −2 | 3.72 / 4.82 | 1.59 / 7.68 | 0.22 / 0.52 | 0.74 | 0.80 | 0.75 |
| Chord stopped by hand, −2 | 3.93 / 5.19 | 0.46 / 0.70 | 0.17 / 0.33 | 0.51 | 0.50 | 0.56 |
| Drop A power chord, −2 | 1.00 / 1.00 | 0.44 / 0.44 | 0.03 / 0.03 | 0.44 | 0.36 | 0.43 |
| Single note E2, +2 | 0.03 / 0.08 | 0.04 / 0.12 | 0.01 / 0.03 | 0.63 | 0.26 | 0.50 |
| Open E chord, +2 | 0.38 / 1.43 | 0.44 / 1.28 | 0.14 / 0.48 | 0.79 | 0.77 | 0.72 |
| Palm mutes 200 bpm, −2 | – | – | – | 0.58 | 0.75 | 0.64 |
| Vibrato A3, −2 | – | – | – | 0.44 | 0.91 | 0.67 |

Hand-mute leftover at 10–30 ms: A −18.1 dB, M −7.7 dB, L −14.2 dB.

Reading: look-ahead makes steady partials 2–5 times cleaner and fixes the hand-over when a new note arrives. But "spec" gets worse on single notes, and the measured attack moves earlier (down to 1.7 ms where 2.0 is expected): the engine plays partials of a note before its attack (pre-echo). Vibrato is better than M but still behind A.

### Offline "Perfect" engine (2026-11-13, PLAN 5.8, `reference/tp_offline.py`)

`python run_tests.py scen off` (engine O). Raw output: `docs/results_offline_raw.txt`.
New measure "fine": spec on a 2.9 Hz grid (16384-point FFT). It is fair for dense chords and blind to phase between partials.
The palm-mute scenario was made fairer on this date: each pick now ends the note before it (`choke`), like a real string. A new "same string run" scenario was added.

| Scenario | A spec | O spec | A fine | O fine | A dist | O dist | O pitch (cents) | O wobble |
|----------|--------|--------|--------|--------|--------|--------|-----------------|----------|
| Single note E2, −2 | 0.30 | **0.02** | 0.24 | 0.00 | 1.78 | 0.26 | 0.01 | 0.00 / 0.00 |
| Single note E2, +2 | 0.63 | **0.04** | 0.30 | 0.00 | 2.65 | 0.38 | 0.00 | 0.00 / 0.00 |
| Low B1, −2 | 0.26 | **0.02** | 0.25 | 0.00 | 1.61 | 0.27 | 0.03 | 0.00 / 0.01 |
| Power chord E5, −5 | 0.58 | **0.11** | 0.91 | 0.01 | 2.99 | 0.96 | 0.11 | 0.00 / 0.01 |
| B5 chord, −2 | 0.45 | **0.17** | 0.65 | 0.03 | 2.50 | 1.67 | 0.33 | 0.02 / 0.04 |
| B5 chord, −5 | 0.50 | **0.22** | 0.81 | 0.04 | 2.80 | 1.73 | – | – |
| Drop A chord, −2 | 0.44 | **0.12** | 0.64 | 0.03 | 2.44 | 1.32 | 0.01 | 0.01 / 0.01 |
| Open E chord, −2 | 0.62 | **0.27** | 0.80 | 0.06 | 2.63 | 1.92 | 0.12 | 0.03 / 0.09 |
| Open E chord, −5 | 0.68 | **0.28** | 0.94 | 0.07 | 2.65 | 1.96 | 0.11 | 0.04 / 0.18 |
| Open E chord, +2 | 0.79 | **0.33** | 0.31 | 0.07 | 3.37 | 2.40 | 0.05 | 0.03 / 0.09 |
| Chord stopped by hand, −2 | 0.51 | **0.30** | 0.75 | 0.13 | 2.15 | 2.15 | 0.05 | 0.02 / 0.06 |
| Chord stopped by hand, −5 | 0.64 | **0.30** | 0.90 | 0.15 | 2.44 | 2.12 | 0.14 | 0.03 / 0.13 |
| Same string run, −2 | 0.49 | 0.36 | 0.55 | 0.39 | 3.08 | 4.11 | – | – |
| Palm mutes 200 bpm, −2 | 0.62 | 0.41 | 0.56 | 0.58 | 2.97 | 3.41 | – | – |
| Vibrato A3, −2 | 0.44 | 0.39 | 0.28 | 0.29 | 2.81 | 2.85 | – | – |
| Strum 15 ms + late note, −2 | 0.74 | 0.63 | 0.80 | 0.19 | 4.02 | 3.93 | 0.26 | 0.19 / 0.65 |

Goal of PLAN 5.8.3 (spec ≤ 0.35): met by 12 of 16. Not met: same string run (0.36, almost), palm mutes, vibrato, strum.

Tests on two sines (`beat_check` in the session scratchpad, worth turning into a unit test): one sine 0.02; two sines 3 / 6 / 10 Hz apart 0.02 / 0.02 / 0.02 (before the beat split: 0.14 / 0.16 / 0.10).

Diagnosis runs with the true pick times given to the engine (cheat, `Offline.process(x, true_attacks=...)`):

| Scenario | Detector | True picks |
|----------|----------|------------|
| Palm mutes | 0.41 | 0.30 |
| Same string run | 0.36 | 0.29–0.31 |
| Strum only (15 ms) | 0.69–0.72 | 0.64–0.67 |
| Vibrato | 0.39 | 0.39 |

So for palm mutes and runs, the attack detector is the limit. For the strum it is not.

Speed: about 15 s of Python work per 1 s of six-string chord.

### What the numbers say

1. M has about 6 to 13 times less chord wobble than A on down-shifts and much better chord pitch, at the same latency. On the +2 chord both are about equal.
2. M is as good as A on single notes.
3. M is worse than A on palm mutes and clearly worse on vibrato. These are the open problems (PLAN 5.6.5).
4. After a hand-mute, M leaves −7.7 dB in the first 10–30 ms (A: −18.1 dB), then silence. Before the fit gate was added this was +2.7 dB with a 100 ms ghost.
5. The "strum + late note" worst value (7.68 dB on one partial) shows a hand-over that is not yet clean when a new note arrives over ringing ones.

### Limits of these numbers

- Synthetic signals only. Real strings have noise, buzz, pitch drift at the attack and sympathetic ringing.
- The wobble measure skips partials that sit within 25 Hz of another partial (they beat, and the measure cannot split them). In a full chord that is most of the upper partials. Both engines are blind there in the same way, so the comparison is fair, but the absolute quality of those partials is unknown.
- Earlier work on this topic found that numbers miss some artifacts. Listening decides.

### Tuning runs worth remembering

| Change | Effect |
|--------|--------|
| Analysis window 4096 → 8192 samples with 2048 fall (engine M) | Open E −2 wobble 2.28 → 0.41 dB. No latency cost. |
| Symmetric Hann 8192 (fall 4096) | Slightly better chords (0.30) but longer lag. Not chosen. |
| Steadiness test `pred_phase_tol` 0.5 / 4.0 / off | Chords 0.55–1.43 / 0.34–0.58 / 0.25–0.49 dB. Vibrato spec 0.68 / 0.91 / 0.98. Default 4.0. |
| Fit gate off | Hand-mute leftover −5.7 dB against −11.4 dB with the gate (at tol 1.5). |
| Engine B, synthesis length 128 → 512 | Wobble at 220 Hz note 7 dB → 0.0 dB. Shows that bin-moving needs a long output window. |

## 2026-11-24 — Doubler, Python reference (PLAN 16)

`python reference/double_tests.py`, defaults of PLAN 16.3, 48 kHz. First table: original untouched (copies
always late). The second table, after it, is the current design (original is a timing-only take). Synthetic guitar with pick noise, through a
tanh amp and a 5 kHz cab low-pass. L = original side, R = double side (for "ours": the copy; latency 0).

| scenario | system | coh low | mid | high | mono dB | bal dB | lag ms | spread ms | picks |
|----------|--------|---------|-----|------|---------|--------|--------|-----------|-------|
| chug   | fixed 12 ms | 0.80 | 0.78 | 0.77 | +2.76 | +0.01 | +12.0 | | |
| chug   | ours        | 0.14 | 0.05 | 0.10 | −0.11 | −0.12 | +1.9 | 2.0 | 23/24 |
| chug   | true double | 0.10 | 0.03 | 0.02 | −0.15 | +0.16 | +6.7 | | |
| chords | fixed 12 ms | 0.82 | 0.80 | 0.77 | +0.07 | +0.00 | +12.0 | | |
| chords | ours        | 0.31 | 0.04 | 0.05 | −1.07 | +0.47 | +3.3 | 2.1 | 4/4 |
| chords | true double | 0.11 | 0.03 | 0.05 | −0.32 | +1.23 | +9.6 | | |
| lead   | fixed 12 ms | 0.84 | 0.78 | 0.78 | −0.67 | +0.00 | +12.0 | | |
| lead   | ours        | 0.60 | 0.28 | 0.08 | +0.58 | −1.10 | +4.6 | 2.4 | 1/12 |
| lead   | true double | 0.39 | 0.19 | 0.06 | +0.49 | +0.41 | +18.2 | | |

"lag ms" of the true double is not reliable: the parts repeat, so the envelope match can lock onto a neighbour note.

Velvet-noise decorrelator (dropped), chords at default timing: coherence 0.21 / 0.04 / 0.06 at decorr 0, 0.1, 0.2
and 0.4 alike; peak of the copy against the input 1.22× / 1.55× / 1.94× / 2.50×. Tight chords (timing 1 ms,
pitch 1 cent): mono +2.38 / +2.18 / +1.86 dB at decorr 0 / 0.4 / 1.0, coherence unchanged.

Pick detection after distortion: `detect_onsets` (full band, ratio 6) finds 1/24 chug, 1/4 chord, 1/12 lead picks.
`detect_picks` (above 1.5 kHz, ratio 4) finds 23/24, 4/4, 1/12. Spectral flux (512 / 64) was worse: 50–160 false
hits on distorted chords.

Original as a timing-only take (current design). "copy 1st" = share of picks where the copy lands before the original.

| scenario | coh low | mid | high | mono dB | bal dB | spread ms | copy 1st | picks |
|----------|---------|-----|------|---------|--------|-----------|----------|-------|
| chug   | 0.05 | 0.06 | 0.07 | +0.58 | +0.14 | 2.8 | 50 % | 23/24 |
| chords | 0.16 | 0.09 | 0.07 | +0.16 | +0.00 | 1.4 | 25 % | 4/4 |
| lead   | 0.59 | 0.22 | 0.05 | −0.64 | +0.09 | 2.1 | 75 % | 1/12 |

Comb inside one speaker (cepstrum peak of L against the input, 0.3–30 ms; higher = more flanger / phaser).
User heard flanger in quad. Defaults, synthetic parts:

| part | ours quad, no velvet | no pitch | timing 25 ms | before amp | band delays 2 ms | velvet 1.0 (15 ms) | true quad |
|------|------|------|------|------|------|------|------|
| chug   | 0.149 | 0.159 | 0.120 | 0.142 | 0.095 | 0.074 | 0.059 |
| chords | 0.156 | 0.183 | 0.105 | 0.165 | 0.086 | 0.067 | 0.049 |
| lead   | 0.138 | 0.144 | 0.106 | 0.114 | 0.098 | 0.083 | 0.057 |

Peak of a copy against the input with velvet 1.0: 15 ms 1.9–2.4×, 8 ms 2.2×, 4 ms 1.9–2.0×; above 1500 Hz instead
of 600 Hz: 1.7–2.0× but comb 0.09–0.12.

Overtone phase drift on the copies (`scratchpad` experiment, not in the engine). Quad comb / peak of a copy:

| part | plain | velvet 1.0 | STFT 2048/256, drift 1 Hz | low-delay S 128 | low-delay S 256 | true quad |
|------|------|------|------|------|------|------|
| chug   | 0.149 | 0.074 | 0.060 / 2.2× | 0.084 / 2.4× | 0.078 / 2.3× | 0.059 |
| chords | 0.156 | 0.067 | 0.053 / 2.2× | 0.074 / 2.5× | 0.069 / 2.2× | 0.049 |
| lead   | 0.138 | 0.083 | 0.066 / 2.1× | 0.166 / 2.2× | 0.109 / 2.6× | 0.057 |

Drift 0.3 / 1 / 3 Hz on the full STFT: chug 0.079 / 0.060 / 0.056, chords 0.060 / 0.053 / 0.051. Per bin
(no smoothing) as good as smooth 6.

## 2026-11-24 — Doubler Studio mode (PLAN 16.7)

`python reference/studio_tests.py`. Spread = std of take 2 against take 1 at the attacks.

| part | system | coh mid | mono dB | comb | copy 1st | spread ms | picks |
|------|--------|---------|---------|------|----------|-----------|-------|
| chug   | live 2   | 0.05 | +0.59 | 0.027 | 50 % | 2.9 | 23/24 +1 |
| chug   | studio 2 | 0.05 | −0.13 | 0.024 | 33 % | 4.8 | 24/24 +1 |
| chug   | true 2   | 0.03 | −0.15 | 0.000 | | | |
| chug   | live 4   | 0.06 | +1.37 | 0.071 | | | |
| chug   | studio 4 | 0.06 | +0.31 | 0.058 | | | |
| chug   | true 4   | 0.05 | +0.39 | 0.059 | | | |
| chords | live 2   | 0.09 | +0.34 | 0.015 | 25 % | 1.4 | 4/4 +2 |
| chords | studio 2 | 0.07 | −0.72 | 0.017 | 0 % | 1.7 | 4/4 +0 |
| chords | true 2   | 0.02 | +0.20 | 0.000 | | | |
| chords | live 4   | 0.13 | +0.75 | 0.072 | | | |
| chords | studio 4 | 0.09 | +0.38 | 0.053 | | | |
| chords | true 4   | 0.04 | +0.68 | 0.049 | | | |
| lead   | live 2   | 0.20 | +0.47 | 0.038 | 67 % | 2.7 | 2/12 +0 |
| lead   | studio 2 | 0.16 | +0.24 | 0.023 | 42 % | 4.1 | 12/12 +1 |
| lead   | true 2   | 0.18 | −0.57 | 0.000 | | | |
| lead   | live 4   | 0.27 | +0.91 | 0.074 | | | |
| lead   | studio 4 | 0.16 | +1.09 | 0.061 | | | |
| lead   | true 4   | 0.20 | +0.77 | 0.057 | | | |

Studio quad presets, comb chug / chords / lead: default 0.062 / 0.053 / 0.062, tight (3 ms, 2 cents) 0.063 /
0.052 / 0.064, loose (20 ms, 12 cents) 0.065 / 0.057 / 0.072, extreme (all max, drift 3) 0.069 / 0.062 / 0.092.
Tight quad mono sum is high on chug (+2.26 dB): the takes are close in time and the low end (below 150 Hz, no drift)
adds up.

Studio after the user heard phaser + left lean. Old `phase_drift` (per bin, never reset): copy level −1.0 / −1.3 /
−2.3 dB (chug / chords / lead); chug double attack sharpness L 6.5, R 1.6 dB (input 6.4); smear before the attack
L −5.9, R −2.7 dB (input −6.1). Studio double L−R +0.74 / +1.59 / +3.14 dB.

`phase_drift_notes` (phase locked, reset at every attack), Studio quad, comb / L−R dB / attack L / R:

| attack detune | chug | chords | lead |
|------|------|------|------|
| none (reset only) | 0.127 / −0.21 / 3.0 / 2.6 | 0.068 / +1.21 / 1.1 / 2.1 | 0.090 / +0.85 / 0.8 / 0.6 |
| 8 cents, 40 ms | 0.082 / −0.25 / 3.6 / 2.1 | 0.063 / +1.26 / 1.6 / 1.6 | 0.078 / −0.55 / 0.5 / 0.7 |
| **15 cents, 40 ms (chosen)** | 0.068 / −0.20 / 4.1 / 2.2 | 0.063 / +1.33 / 0.8 / 2.0 | 0.077 / −0.61 / 0.5 / 1.1 |
| 25 cents, 40 ms | 0.065 / −0.13 / 4.7 / 1.7 | 0.062 / +1.40 / 1.4 / 5.9 | 0.080 / −0.99 / 0.6 / 1.1 |
| 40 cents, 20 ms | 0.062 / −0.12 / 4.6 / 1.8 | 0.063 / +1.39 / 0.5 / 6.2 | 0.076 / −0.72 / 0.9 / 0.5 |
| true quad | 0.059 / −0.34 / 2.8 / 3.6 | 0.049 / −0.21 / 1.2 / 4.1 | 0.057 / +1.78 / 0.7 / 0.5 |

Studio double with reset + 8 cents: L−R −0.16 / +0.73 / +0.12 dB, attack L / R chug 7.6 / 6.7 dB.

## 2026-11-24 — Doubler "analyse and play again" on the DI (PLAN 16.8)

`python reference/resynth_tests.py` (about 7 minutes). Each take through its own amp (tanh, drive 6 / DI peak, cab
5 kHz). Analysis check: error −252 … −264 dB, residual −25.3 / −23.7 / −26.0 dB of the input (chug / chords / lead).

| part | system | coh mid | mono dB | comb | L−R dB | atk L / R |
|------|--------|---------|---------|------|--------|-----------|
| chug   | bend 2      | 0.04 | +0.10 | 0.030 | +0.02 | 6.6 / 4.8 |
| chug   | resynth 2   | 0.03 | +0.17 | 0.030 | +0.02 | 6.6 / 3.3 |
| chug   | true 2      | 0.03 | −0.17 | 0.000 | +0.02 | 6.4 / 4.8 |
| chug   | bend 4      | 0.06 | +0.43 | 0.069 | +0.02 | 3.8 / 1.9 |
| chug   | resynth 4   | 0.06 | +0.32 | 0.068 | −0.38 | 2.9 / 3.0 |
| chug   | true 4      | 0.06 | +0.41 | 0.057 | +0.14 | 4.6 / 3.1 |
| chords | bend 2      | 0.03 | +0.19 | 0.023 | +0.48 | 1.3 / 3.0 |
| chords | resynth 2   | 0.04 | +0.19 | 0.023 | +0.02 | 1.3 / 0.3 |
| chords | true 2      | 0.07 | +0.68 | 0.000 | −0.10 | 1.2 / 16.6 |
| chords | bend 4      | 0.06 | +0.86 | 0.058 | +0.23 | 3.2 / 1.0 |
| chords | resynth 4   | 0.08 | +0.41 | 0.061 | +0.23 | 1.7 / 1.8 |
| chords | true 4      | 0.07 | +0.71 | 0.058 | −0.29 | 2.9 / 1.3 |
| lead   | bend 2      | 0.18 | −0.98 | 0.027 | +0.04 | 0.7 / 1.2 |
| lead   | resynth 2   | 0.18 | +0.05 | 0.027 | −0.17 | 0.7 / 1.2 |
| lead   | true 2      | 0.21 | +0.13 | 0.000 | +0.06 | 0.9 / 0.6 |
| lead   | bend 4      | 0.19 | +0.57 | 0.073 | −0.06 | 1.0 / 0.8 |
| lead   | resynth 4   | 0.17 | +0.88 | 0.108 | +0.68 | 0.6 / 1.0 |
| lead   | true 4      | 0.17 | +0.25 | 0.064 | −0.37 | 0.5 / 0.2 |

Lead quad, no timing changes: new phases + new residual 0.098 / 0.106 / 0.101 (3 seeds); new phases + old residual
0.067 / 0.065 / 0.063; old phases + new residual 0.060. Noise hop 64 / 32 / 16: 0.098 / 0.100 / 0.099; the comb
peak sits at 3.4–3.5 ms (median), the period of the lead notes, so it is not a delay comb.

