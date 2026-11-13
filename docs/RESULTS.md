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
