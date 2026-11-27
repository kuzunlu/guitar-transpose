# Guitar Transpose Plugin — Master Plan

Date: 2026-11-12
Status: the algorithm is proven in a Python reference (`reference/`). No C++ and no plugin exist yet.
**Read section 0A first. It changes parts of the original plan.**

This file is the single source of truth for the project.
It is written so that a coding model can pick up any milestone and build it.

---

## 0. Rules for the coding model (read first)

1. Follow the user's global rules in `~/.claude/CLAUDE.md`. The most important ones here:
   - Ask before committing, pushing, running the app, or anything hard to undo.
   - Commit messages are one short title line. No body. No Claude attribution.
   - Pin every dependency to an exact tag or commit hash. Never a branch name, never "latest".
   - Make the smallest change that does the job. Do not restructure code you were not asked to touch.
   - Write to the user in plain, simple English.
2. Work one milestone at a time, in order. Do not start the next one until the "Done when" list passes.
3. At the end of each milestone: stop, write the numbers into `docs/RESULTS.md`, tell the user, and ask them to listen.
4. Every number in this plan marked "start value" is a first guess. Tune it with the test harness (section 8), not by feel.
5. Parts marked **[PROVEN]** are known methods. Parts marked **[BET]** are my own design and are not tested yet. Each bet has a gate. If the gate fails, use the fallback written next to it.
6. Never put GPL code into the plugin. See section 10.
7. Do not add Python packages without asking the user. NumPy is installed. SciPy is not.
8. When a decision is made that is not in this plan, write one line about it in `docs/DECISIONS.md`.
9. The Python files in `reference/` are the spec for the DSP. The C++ must give the same numbers on the same test signals. If the C++ and the reference disagree, the C++ is wrong until proven otherwise.

---

## 0A. Where the project stands (after the prototype of 2026-11-12)

### What was done

The whole Live engine was built and measured in Python + NumPy, in `reference/`:

| File | What it is |
|------|------------|
| `tp_ref.py` | The engines. `Predictive` is the chosen Live engine. `Varispeed` and `detect_onsets` are its parts. `Hybrid` is the rejected first design, kept for its tests. |
| `synth.py` | Synthetic guitar with a known perfect answer (section 8.2). |
| `metrics.py` | The measurements (section 8.3). |
| `run_tests.py` | Runs everything and prints the tables. `python run_tests.py all` |
| `wavio.py`, `render.py` | Transpose a real WAV file to listen: `python render.py in.wav out.wav -2` (add `O` for the offline engine, `A` for varispeed) |
| `tp_offline.py` | The offline "Perfect" engine (section 5.8.4). |

Numbers: `docs/RESULTS.md`. Decisions: `docs/DECISIONS.md`.

### What changed against the original plan

1. **Bet #1 failed.** The bin-moving spectral engine of section 5.3 gives 4–9 dB wobble on real notes. The cause is in section 5.7. Do not build 5.3 or 5.4 for Live mode.
2. **The hand-over idea of section 5.1 is proven** (two paths add up within 0.18 dB). It is the base of the new engine.
3. **The Live engine is now the predictive engine of section 5.6.** It measures the partials, predicts them forward as sine waves, subtracts the prediction from the input, and sends what is left through the varispeed of section 5.2. No audio goes through the spectrum, so the spectrum adds no delay.
4. **Latency is lower than planned:** 96 samples (2.0 ms) for down-shifts, 336 samples (7.0 ms) for up-shifts, at 48 kHz.
5. Chord wobble with the predictive engine is 0.3–0.6 dB, against 3.5–7.2 dB for varispeed alone, on synthetic chords.

### What is not done and not known

- Nothing has been tested on a real guitar. Nobody has listened yet. This is the first thing to do (milestone M2.5).
- Three open problems in the predictive engine: vibrato, palm mutes, and a new note over ringing notes (section 5.6.5).
- CPU cost in C++ is unknown. The reference is about 5 times slower than real time, but it is Python and uses a very large FFT.
- No baseline (Signalsmith, HyperTune, pedals) has been measured yet.

### Machine setup still needed

On 2026-11-12, with the user's OK, the C++ workload was added to **Visual Studio Build Tools 2026** at `C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools`. Verified by building and running a test program:
- MSVC 14.51.36231 (`_MSC_VER` 1951), C++20
- Windows SDK 10.0.26100.0
- CMake 4.3.1 and Ninja, both inside the Build Tools folder (not on PATH until `vcvars64.bat` is called)
- `vcvars64.bat` prints "'vswhere.exe' is not recognized". This is harmless.
Do **not** use the "Insiders" install at `C:\Program Files\Microsoft Visual Studio\18\Insiders`: it is a preview that expired on 2026-09-23 and is retired on 2026-12-22.
To build from a shell, first load the compiler settings with `"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"`, or use CMake's Visual Studio 18 generator.

---

## 1. Goal

A VST3 plugin that transposes (pitch shifts) an electric guitar DI signal.
It sits first in the chain, before the amp simulator.

Targets, in order of importance:

| # | Target | Number |
|---|--------|--------|
| 1 | Feels instant when playing | Attack latency ≤ 3 ms for down-shifts (48 kHz) |
| 2 | Sounds like a real guitar in that tuning | Beats every low-latency baseline in our tests (section 8) |
| 3 | Works on chords, not just single notes | No audible warble on sustained chords at −1 to −5 semitones |
| 4 | Survives high gain | Scores are also measured after a distortion stage |
| 5 | Light on CPU | < 5 % of one core at 48 kHz |

Main use: −1 to −7 semitones (drop tunings). Full range: −12 to +12.
Up-shifts are harder than down-shifts for a physical reason (section 5.2). They get a slightly higher latency.

For comparison, what exists today (from web research, November 2026):

| Product | Latency | Source of number |
|---------|---------|------------------|
| DigiTech Drop | 12–17 ms | reported, method unknown |
| Boss XS-1 | 13–14 ms | measured by a reviewer |
| EHX Pitch Fork | 16–22 ms | claimed |
| Klowra Vein / Dive | 10–12 ms / ~8 ms | measured / reported |
| Hotone Freqlux | 4–5 ms | maker's claim |
| Mooer Pitchbox | 19 ms | measured by a forum user |
| Polychrome DSP HyperTune (plugin) | "near zero" | maker's claim, no number |
| Neural DSP plugin Transpose | noticeable; **not polyphonic** | forum reports |
| zplane reTune (plugin) | 140 ms | maker's spec |
| "Rollers" paper (Juillerat 2008) | < 10 ms | paper |
| Juillerat & Hirsbrunner STFT paper | 12 ms | paper |

So ≤ 3 ms with good chords would be better than anything with a published number.
HyperTune is the one to beat. The user should get its demo for A/B tests.

---

## 2. Glossary (plain words)

- **DI**: the dry guitar signal, straight from the guitar, before any amp.
- **Partial**: one single sine tone inside a note. A guitar note is a sum of many partials (the fundamental and its overtones).
- **Tonal part**: the steady partials of ringing notes.
- **Residual**: everything that is not steady partials: pick attack, noise, notes that just started, bends in motion.
- **Latency**: how late the output is compared to the input.
- **Varispeed**: playing audio slower or faster, like a tape. It changes pitch perfectly but also changes speed.
- **Splice**: a jump of the read position in a delay buffer, hidden by a short crossfade.
- **STFT**: cutting the signal into short overlapping frames and taking the FFT of each. Gives a picture of which frequencies are present at each moment.
- **Hop (H)**: how many samples we move forward between two frames.
- **Phase vocoder (PV)**: a pitch shifter that works on STFT frames.
- **Peak**: a local maximum in a frame's spectrum. Each steady partial shows up as one peak.
- **Mask**: a number from 0 to 1 per frequency bin. Here it says "how tonal is this bin".
- **PDC**: plugin delay compensation. The DAW shifts tracks to hide a plugin's latency. Works on playback, not while you play live.
- **Ratio r**: `r = 2^(semitones/12)`. −1 semitone → r = 0.9439. −12 → r = 0.5. +12 → r = 2.

---

## 3. What exists, and where the room for improvement is

### 3.1 The hard limit that nobody can beat

To tell two partials apart that are Δf Hz apart, you must observe about 1.5/Δf to 2/Δf seconds of signal.
A power chord on the low E string has partials 41 Hz apart. That needs 40–50 ms of signal.

Old designs pay for this with latency: they wait 20–50 ms before output.

The key idea of this plan: **observing 50 ms does not mean delaying 50 ms.**
We can look at the last 85 ms (the past) and still output with ~3 ms delay.
The price is that for the first 20–40 ms of a brand-new note we do not yet know its partials.
So for that short time we need a method that needs no knowledge at all. Varispeed is exactly that.

### 3.2 Existing algorithm families

| Family | How it works | Good at | Bad at |
|--------|--------------|---------|--------|
| Time domain (OLA, SOLA, WSOLA, PSOLA, old Whammy) | Varispeed plus splices | Single notes, attacks, near-zero latency | Chords: splices cut partials at wrong phases → warble, flam |
| Phase vocoder (classic, phase-locked, Rubber Band, Signalsmith, Bungee, élastique) | Edit STFT frames | Chords, sustained sound | Latency 40–140 ms, soft attacks, "phasey" tone |
| Filter bank + frequency shift per band ("Rollers") | Many narrow IIR bands, each shifted by a fixed Hz amount | < 10 ms latency | A partial between two bands is shifted twice by different amounts → beating |
| Sines + transients + noise (STN) models | Split signal in 3 parts, treat each its own way | Best offline quality | Published versions are offline and not causal |
| Neural (RAVE/BRAVE, DDSP, neural vocoders) | A network generates the audio | Timbre transfer, voice | Not transparent, heavy, no clean training pairs (section 9) |

Open-source libraries we can test against:

| Library | License | Use in this project |
|---------|---------|---------------------|
| Signalsmith Stretch | MIT | Baseline, and first "Studio" engine inside the plugin |
| Bungee | MPL-2.0 | Baseline in the test harness only |
| SoundTouch | LGPL-2.1 | Baseline in the test harness only |
| Rubber Band (R3) | GPL or paid | Baseline as a **separate command-line program only**. Never linked into our code. |

### 3.2.1 What a study of this exact problem found

Patrick Nolte's master's thesis (HAW Hamburg, 2021) tested these families on polyphonic electric guitar with a 10 ms latency goal. His results:

- WSOLA (time domain): high quality and good attacks on single notes and light chords. Fails on full chords. About 20 ms minimum, even for single notes.
- Phase vocoder: handles full chords, but at 10 ms the peaks cannot be told apart. It needed about 43 ms for light chords and about 85 ms for full chords. He judged both as not usable live.
- Rollers: the narrow low-frequency filters cause more than 50 ms of delay in the bass. Making them faster gives a detuned sound and strong amplitude wobble.
- Constant-Q transform: fails at this latency.
- Objective numbers did not show the artifacts well. A listening test was needed.
- His outlook: a guitar's tone colour (spectral envelope) changes over the fretboard, and even élastique Pro ignores this. Learning it from the real instrument would make shifts sound more natural.

How this plan answers each point:

- The 85 ms he needed is the same window this plan uses (N = 4096 at 48 kHz). But in his tests the latency was equal to the window. Here the window looks into the past and the output delay is only S (section 5.3.1).
- The time-domain weakness on chords is removed by sending steady partials to the tonal path (section 5.4).
- The time-domain strength on attacks is kept, and its 20 ms is cut by onset re-sync (section 5.2).
- His warning about objective numbers is why every gate in this plan ends with a listening test by the user.
- His outlook matches section 6 (timbre fix) and research item R3.

### 3.2.2 Newer work (2023–2026)

The core math of pitch shifting is from 1999–2010. Newer work mostly targets offline time-stretching, voice, or neural timbre transfer. A search on 2026-11-12 found no published 2024–2026 method that does clean chords at a few ms of latency. The best low-latency results are closed products (HyperTune, the pedals). The search was not complete, so check again before M4.

What the newer work says, and what we take from it:

| Work | What it is | What we take from it |
|------|------------|----------------------|
| Polak & Erkut, "Low-latency Pitch-Shifting with STN decomposition" (DAGA 2025) | The closest published idea to our Hybrid. A real-time plugin: split into sines / transients / noise with past-only median filters; sines go to Signalsmith's phase vocoder; transients pass unshifted; noise is re-made with random phases. | Its "low latency" is 166 ms, so it is not for live playing. In a blind test it scored **below** plain Signalsmith. The authors blame the past-only median filter (worse split), level errors between the parts, and suggest one frame of look-ahead. This is a direct warning for Bet #2. See the notes under this table. |
| Moliner, Fierro, Wright, Hämäläinen, Välimäki, "Noise Morphing for Audio Time Stretching" (IEEE SPL 2024) | Better handling of the noise part at large stretch factors. | Not needed in Live mode (our residual path is true varispeed, not re-made noise). An option for Studio mode at large shifts. |
| Luff, "The Design of Signalsmith Stretch" (2023 write-up) | How the Studio baseline works: phase is predicted from both time and frequency neighbours. | Read before M4. Its phase prediction is an option if peak tracking in Engine B proves fragile. |
| Cycfi Research (Joel de Guzman), "Zero Latency Pitch Shifting" (June 2026) and "BACF Pitch Shifter" (November 2026), blog posts, code promised as open source | A time-domain shifter for guitar. Splices are spaced by the chord's **common period** (about 24 ms for an open E chord), found with a very cheap 1-bit autocorrelation. Tone is corrected with a spectral envelope (LPC) that is learned from the player's own guitar, with a "learn" button. | Confirms Engine A's 25 ms search range and the Calibrate idea (6.1). Two options to test: 1-bit autocorrelation for the coarse splice search, and a learned LPC envelope as a second form of the timbre fix. Check its license when the code is out. |
| Caspe et al., BRAVE (2025) | Neural timbre transfer under 10 ms. | Shows where neural audio is: fast enough now, but it changes the sound. Not a transparent shifter (section 9). |
| Riou et al., PESTO (2025) | Neural pitch detector, under 10 ms, causal. | Possible helper for research item R2 (grouping partials into notes). Single-pitch only. |
| STSM-FiLM (2025), neural time-stretch for speech; "Low-Latency Neural Models for Real-Time Music Enhancement" (2026) | Neural, causal, but for speech or for clean-up tasks. | Nothing to use directly. |

Notes on the Polak & Erkut result, because our Hybrid is in the same family:

- Their split errors hurt more than ours should. In their design a wrongly sorted bin is either not shifted at all (transient path) or gets random phase (noise path). In ours, both paths shift the pitch correctly and stay in phase (section 5.4.3), so a wrong mask value costs less.
- Still, treat the past-only mask as the weakest part. Test it early in M5 with the "true mask" check of section 9.3. If the gap is large, try 1–2 frames of look-ahead (costs 0.7–1.3 ms) before anything else.
- They found that Signalsmith changes the output level in an uneven way. Measure this in M1 and correct the gain if needed.
- Level errors between the parts broke their "nothing is lost" property. Our unit test "r = 1 returns the input" (section 8.4) guards against this. Keep it passing at every step.

### 3.3 Where the room is

1. **Nobody public combines the two worlds at low latency.** Time-domain is perfect for new and unstable sound. Spectral is perfect for steady partials. One 2025 paper splits the signal this way in real time, but at 166 ms and with a quality loss (section 3.2.2). Section 5 does it at about 3 ms and hands partials over from one path to the other without a phase jump.
2. **Long look-back, short output window.** Speech-enhancement research (Mauler & Martin 2007) uses a long analysis window with a short synthesis window. This gives fine frequency detail with a few ms delay. Pitch shifters have not used this much.
3. **Onset re-sync.** A splice placed exactly at a pick attack is hidden by the attack. Short notes (palm mutes) can then play as pure varispeed with no splice at all.
4. **Guitar-specific timbre fix.** On a real down-tuned guitar the pickup's resonance peak (2–5 kHz) does not move. A shifter moves it down, so the tone gets dull. A small EQ can put it back (section 6).
5. **Two modes.** A recorded DI track does not need low latency (the DAW hides it with PDC). So "Studio" mode can use 100+ ms and reach the top quality. "Live" mode is for playing.

### 3.4 Verdict on the "record many samples and train an AI" idea

Short answer: **not as the main engine. Yes as a helper later.** Full reasoning is in section 9.

Neural DSP's amp models work because an amp is easy to learn: send any signal in, record what comes out, and you have perfect training pairs.
For pitch shifting there are no such pairs. You cannot play the exact same performance, sample for sample, in two tunings.
And a network that generates the waveform is not "transparent": it adds its own noise and phase errors, which a high-gain amp after it makes much louder.

Your recordings are still very valuable. They are the test set, the realism reference, and later the training data for a small helper network (section 9.3).

---

## 4. Product shape

- Formats: VST3 (the only format the user needs) and Standalone (for quick tests only). No AU, AAX or CLAP. Windows first. Keep the code portable for macOS later.
- Host: **Ableton Live** (the user's DAW). Test every milestone there first.
  - Ableton reads the latency from the VST3 and compensates on playback (PDC).
  - When monitoring a live input, Ableton adds plugin latency to what you hear unless the user turns on "Reduced Latency When Monitoring" (Options menu). Tell the user about this option in M1. Our 2 ms is only worth something if the rest of the chain is fast too.
  - Ableton calls `setLatencySamples` changes only at some moments; test that a change from down-shift to up-shift (96 → 336 samples) is picked up.
  - Automation: test Transpose automation from an Ableton clip envelope.
- Framework: JUCE with CMake. The VST3 SDK is MIT-licensed since version 3.8 (October 2025), and JUCE bundles it.
- Input: mono or stereo. Guitar DI is mono. For stereo, make the decisions (onsets, splices, masks) on L+R and apply the same to both channels.

Parameters:

| Name | Range | Default | Notes |
|------|-------|---------|-------|
| Transpose | −12 … +12 semitones, whole steps | 0 | At 0 (and Fine 0) the audio passes through untouched, with the same delay |
| Fine | −50 … +50 cents | 0 | |
| Mode | Live / Studio | Live | Changes reported latency |
| Timbre | 0 … 100 % | 0 until M6 | Pickup resonance fix (section 6) |
| Pickup Freq | 1.5 … 6 kHz | 3.5 kHz | Used by Timbre |
| Range | — | — | Not needed. The user plays 6- and 7-string only (lowest open note B1 = 61.7 Hz, or A1 = 55 Hz in drop A). The 8192-sample measuring window resolves this. No bass or 8-string support. |
| Mix | 0 … 100 % | 100 % | Dry path must be delayed by the reported latency |
| Output | −24 … +12 dB | 0 | |

Latency reported to the host (48 kHz, start values):

| Case | Latency |
|------|---------|
| Live, shift down or 0 | 96 samples (2.0 ms). This is the varispeed rest delay of the predictive engine (5.6). |
| Live, shift up | 96 + 240 samples runway = 336 samples (7.0 ms) |
| Studio | whatever the Studio engine needs (~100 ms) |

The latency changes only when Mode changes or Transpose crosses zero. Call `setLatencySamples` then, never per block.

---

## 5. The Live engine

### 5.1 The one idea that ties it together

A pitch shift by ratio r is the same as **a delay that keeps changing**:
the delay `d` (in samples) grows by `(1 − r)` every sample. (For up-shifts it shrinks.)

- The **residual path** (5.2) uses one real delay line for the whole signal. The delay cannot grow forever, so it must jump back sometimes. That jump is the splice. It is harmless on noise and attacks, and harmful on steady partials.
- The **tonal path** (5.3) gives **each partial its own delay**. For a steady sine of frequency ω, a delay d is just a phase turn of `−ω·d`. A phase can wrap around freely, so a partial never needs a splice.

So both paths do the same thing, in two ways. That is why a partial can move from one path to the other without a jump: we set its phase turn to `−ω·d_A`, where `d_A` is the delay the residual path has right now.

```
            ┌────────────── onset detector (on raw input) ───────────────┐
            │                                                            │
in ──► low-delay STFT ──► peaks + tonal mask m (0..1 per bin)            │
            │                                                            ▼
            ├── m·X ──────► TONAL PATH: move each peak region,     RESIDUAL PATH:
            │               per-partial phase turn ──► ISTFT ─┐    varispeed delay line
            │                                                 │    with onset re-sync
            └── (1−m)·X ──► ISTFT ──► residual e(t) ──────────┼──► and splices
                                                              ▼         │
                                                             sum ◄──────┘ ──► timbre EQ ──► out
```

Two special cases fall out for free, and they are the first two engines we build:

- mask m = 0 everywhere → only the residual path runs → **Engine A** (pure time domain).
- mask m = 1 everywhere → only the tonal path runs → **Engine B** (pure low-delay phase vocoder).
- adaptive mask → **Hybrid** (the real product).

### 5.2 Engine A — varispeed with onset re-sync  **[PROVEN parts, simple]**

All sizes are for 48 kHz. Scale by `fs/48000` for other rates.

State:
- Circular buffer of input samples. Length ≥ 8192.
- `d`: current delay in samples (float).
- `D_min` = 12 samples. Needed by the interpolator (it reads a few samples after the read point).
- `D_max` = 960 samples (20 ms). Start value.
- `R_up` = 240 samples (5 ms). Runway for up-shifts. Start value.

Per output sample:
1. `out = interpolate(buffer, writePos − d)`. Use a 16-tap windowed-sinc polyphase interpolator (Kaiser window, 64 phases, linear blend between phases). Not linear or cubic: they dull the tone.
2. `d += (1 − r)`.

Rest position `d_rest`: `D_min` for down-shifts, `D_min + R_up` for up-shifts.

Why up-shifts need a runway: for r > 1 the read point moves faster than new audio arrives. It would hit "now" and run out of signal. So it must start a bit behind. That start distance is extra latency. This is physics, not a flaw of the method.

Three events move `d` back to (near) `d_rest`:

**(a) Onset re-sync.** When the onset detector fires, crossfade over 48 samples (1 ms) to a new read point at `d_rest`. The attack hides the jump. After that the note plays as pure varispeed, with no splice, for as long as `d` stays inside the limits.
   Example: −2 semitones, `d` grows 0.109 samples per sample. It takes 180 ms to reach 20 ms. A palm-muted note is over by then. So it gets zero splices.

**(b) Idle re-sync.** When the signal fed to Engine A is quiet (short-term RMS under a threshold; in the Hybrid: residual is 30 dB under the tonal part), jump to `d_rest` at once with a 1 ms crossfade. Nobody hears it. This keeps the engine ready, so legato notes (hammer-ons) that have no sharp attack still start with almost no delay.

**(c) Forced splice.** When `d > D_max` (down-shift) or `d < D_min` (up-shift) and neither (a) nor (b) happened:
   - Candidates: new delays `d'` from `d_rest` to `d_rest + 1200` samples (25 ms, one period of 40 Hz).
   - For each candidate, compare the 480 samples (10 ms) of signal **before** the current read point with the 480 samples before the candidate read point. Use normalized cross-correlation. Comparing the past (not the future) is what makes it causal.
   - To save CPU: search on a 4× decimated copy first, then refine ±4 samples at full rate.
   - Pick the best match. Among near-equal matches (within 2 %) prefer the smallest `d'`.
   - Crossfade from old to new read point over 192 samples (4 ms), equal-power if correlation < 0.5, linear otherwise.

Onset detector (start version, runs on the raw input, sample by sample):
- Fast envelope: rectify, attack 0.2 ms, release 5 ms.
- Slow envelope: attack 20 ms, release 20 ms.
- Fire when `fast > 2.0 × slow` and `fast > −50 dBFS`. Then block new triggers for 25 ms.
- Later upgrade (M5): spectral flux from the STFT frames.

Expected result of Engine A alone: excellent single notes, riffs and palm mutes. Sustained chords will warble at each forced splice. That is the known weakness of time-domain shifters, and it is what the tonal path removes.

### 5.3 Engine B — low-delay peak-locked phase vocoder  **[BET #1 — TESTED, REJECTED for Live]**

> Result: the window pair works (input comes back exactly, delay S − 1) and a single sine is shifted cleanly (side tones −95 dB). But on real notes the wobble is 4–9 dB. Section 5.7 explains why. Sections 5.3 and 5.4 stay here as a record. Build section 5.6 instead.

Sizes at 48 kHz (start values): frame length `N = 4096` (85 ms), synthesis length `S = 128` (2.7 ms), hop `H = 32` (0.67 ms).

#### 5.3.1 Low-delay STFT (long look-back, short output)

Frame sample index `n = 0 … N−1`, oldest sample first. No fftshift.

- Analysis window `a[n]`, length N, lopsided:
  - Rise, for `n < N − S/2`: `a[n] = sin²( (π/2) · n / (N − S/2) )` (slow rise from 0 to 1).
  - Fall, for the last S/2 samples: `a[n] = sin( π·k/S )` with `k = n − (N − S)` (so k runs S/2 … S−1; falls from 1 to 0).
- Target product on the last S samples: `p[k] = sin²(π·k/S) · (2H/S)`, k = 0 … S−1. (A Hann window scaled so that overlapped copies at hop H sum to 1.)
- Synthesis window, only on the last S samples: `s[k] = p[k] / a[N − S + k]`. It is zero for the rest of the frame. Guard the division where `a` is tiny (it is not tiny inside this range except at the very last sample, where `p` is also 0; set `s = 0` there).
- Per hop: take the newest N input samples, multiply by `a`, FFT → `X[b]`. Edit. Inverse FFT. Take only the last S samples, multiply by `s`, overlap-add into the output.
- Delay of this STFT is S samples. Verify with an impulse.

Unit test (must pass before anything else in Engine B): with no edit, output = input delayed by exactly S samples, error below −100 dB.

#### 5.3.2 Peaks and regions (per frame)

1. Magnitude `M[b] = |X[b]|`.
2. Peaks: bins that are larger than their 2 neighbours on each side, above −80 dBFS, and above (frame max − 70 dB). Keep at most 150, strongest first. Ignore bins below 30 Hz.
3. Region of a peak: all bins from the lowest-magnitude bin between it and the previous peak, up to the lowest-magnitude bin between it and the next peak. Every bin belongs to exactly one region.
4. True frequency of peak k at bin `b_k`, from the phase change since the last frame:
   `ω_k = 2π·b_k/N + princarg( ∠X_j[b_k] − ∠X_{j−1}[b_k] − 2π·b_k·H/N ) / H`  (radians per sample; `princarg` wraps to −π…π).
5. Track peaks across frames: match each peak to the nearest peak of the last frame if within max(1 bin, 3 % of frequency). A matched peak keeps its state. An unmatched peak is "new".

#### 5.3.3 Per-partial phase turn (this is the pitch shift)

Each tracked peak k carries one number: `Θ_k`, its phase turn. Think of it as `−ω_k × (that partial's own delay)`.

- Update each frame: `Θ_k += (r − 1) · ω_avg · H`, where `ω_avg` is the mean of this frame's and last frame's `ω_k`. Wrap to −π…π.
- New peak: `Θ_k = −ω_k · d_A`, where `d_A` is Engine A's current delay. In "Engine B alone" tests, use `d_A = 0`.

Move the region:
- Shift in bins: `δ_k = (r − 1) · ω_k · N / (2π)`. Integer part `s_k = round(δ_k)`. Leftover `ε_k = δ_k − s_k`.
- Chunk centre index `n_c = N − S/2`.
- For every bin b in region k: `Y[b + s_k] += X[b] · exp( j·(Θ_k − 2π·s_k·n_c/N) )`. Drop bins that land outside 0 … N/2.
- The term `−2π·s_k·n_c/N` is needed because moving bins by `s_k` also turns the phase at the chunk centre; this removes that side effect so that `Θ_k` alone sets the phase there.

Why whole-bin moves are good enough here: the output chunk is only S samples long, so the small frequency error of a whole-bin move (at most half a bin) causes a phase error of at most `π·S/(2N)` = 0.05 rad at the chunk edges. The exact phase `Θ_k` fixes it again every hop.

Sideband test: feed a 997 Hz sine, shift −1 semitone. Any spurious tone must be 60 dB below the main tone.
If it fails, add the first-order fix: run a second FFT of the same frame with the window `a[n]·(n − n_c)` → `X_t[b]`, and use `X[b] + j·(2π·ε_k/N)·X_t[b]` in place of `X[b]` in the move formula. (This is the "time-ramped window" trick from reassignment methods. It applies the leftover fractional shift to first order.)

**Gate for Bet #1** (Engine B alone, mask = 1):
- Sustained synthetic chords (section 8.2) at −1, −2, −5: spurious amplitude wobble of partials (AM metric) lower than Engine A's.
- Pitch error of steady partials < 2 cents.
- Power chord E2+B2 at −5: both notes within 5 cents (this checks the 85 ms window resolves 41 Hz spacing).
- Attacks will be soft in this mode. That is expected and is not part of this gate.

**Fallback if Bet #1 fails** (too much roughness from the short synthesis window): raise S to 256 then 512 (5.3 / 10.7 ms) and retest. If still bad at S = 512, replace Engine B with a standard symmetric-window peak-locked phase vocoder at N = 2048, and accept ~20 ms on the tonal path while the residual path keeps attacks at ~3 ms. Write the choice in `docs/DECISIONS.md`.

### 5.4 Hybrid — tonal mask and hand-over  **[BET #2 — first form REJECTED, hand-over rule PROVEN]**

> Result: the split through the STFT inherits the fault of 5.3. The hand-over rule of 5.4.3 is correct and is used by section 5.6. The mask of 5.4.1 is also used there.

#### 5.4.1 Tonal mask (causal, no look-ahead)

Per frame, per bin, from magnitudes only:
1. Time median `Ht[b]`: median of `M[b]` over 9 past frames, taken every 4th hop (so it spans about 24 ms with H = 32; tune the span between 20 and 50 ms). Steady partials give a high value. New sound gives a low value.
2. Frequency median `Vf[b]`: median of this frame's `M` over bins `b−8 … b+8`. Flat spectra (noise, clicks) give a value near `M[b]`. Sharp peaks give a low value.
3. Tonalness `Rs[b] = Ht² / (Ht² + Vf² + tiny)`.
4. Raw mask: 0 below `β_lo = 0.6`, 1 above `β_hi = 0.8`, smoothstep in between.
5. Use one mask value per region: the raw mask at the peak bin. Smooth it per tracked peak over time: rise time 10 ms, fall time 3 ms. Call it `m_k`.

(This is a causal version of the "fuzzy" sines/transients/noise split by Fierro & Välimäki, which itself builds on Fitzgerald's median filtering.)

#### 5.4.2 Split and paths

- Tonal spectrum: `m_k · X[b]` for each bin in region k → Engine B edit (5.3.3) → inverse STFT → `y_tonal`.
- Residual spectrum: `(1 − m_k) · X[b]` → inverse STFT with **no edit** → residual signal `e(t)` → Engine A → `y_res`.
- Output = `y_tonal + y_res`.
- Because `m + (1 − m) = 1`, nothing is lost: with r = 1 the sum is the input, delayed.

Both paths share the same STFT delay S, so they stay aligned.
The onset detector reads the raw input, which is S samples ahead of `e(t)`. So Engine A knows about an onset S samples before it arrives. Delay the trigger by S minus 48 samples so the re-sync lands just before the attack.

#### 5.4.3 Hand-over rules (keep both paths in phase)

- A new peak starts with `Θ_k = −ω_k · d_A` (5.3.3). While its mask rises from 0 to 1, both paths play the same partial with the same phase, so they add up cleanly.
- When Engine A jumps (any re-sync or splice, `d_A` changes by a step): for every peak with `m_k < 0.5`, set `Θ_k = −ω_k · d_A(new)` again. Leave peaks with `m_k ≥ 0.5` alone.
- Engine A should avoid forced splices while any strong peak has `0.2 < m_k < 0.8` (a partial is in the middle of moving over). Let `d` run up to `1.5 × D_max` in that case.

What each kind of sound does in the Hybrid:

| Sound | Where it goes | Result |
|-------|---------------|--------|
| Pick attack | residual | True varispeed, ~3 ms late, sharp |
| First 20–40 ms of a note | residual, then moves to tonal | No wrong-pitch blip, no splice |
| Ringing note or chord | tonal | No splices at all → no warble |
| Palm mute, fast riff | residual, re-synced at each attack | Pure varispeed per note |
| Bend, vibrato, slide | mask stays low → residual | Behaves like a good time-domain shifter |
| Noise, hum | residual | Splices are inaudible on noise |

**Gate for Bet #2:** on the full test set (section 8), the Hybrid's total score must beat both Engine A and Engine B on at least 80 % of the items, and must not lose to either by more than a small margin on any single item class. Then a blind listening test by the user: Hybrid vs HyperTune demo vs Engine A.

**Fallback if Bet #2 fails:** use time switching in place of the mask split. Engine A plays for a fixed time after each onset (start: 40 ms), then crossfades over 15 ms to Engine B, with every `Θ_k` set to `−ω_k·d_A` at the start of the crossfade. Simpler, and it still uses the hand-over formula. If that fails too, ship Engine A in Live mode (it is already in the class of the hardware pedals) and Signalsmith in Studio mode.

### 5.5 Studio mode

M1 ships Signalsmith Stretch as the Studio engine (MIT license, good quality, ~100 ms; measure the real number).
After M5, test the Hybrid with look-ahead (S = 1024, mask medians centred in time). Keep whichever scores better.

### 5.6 Predictive engine — the chosen Live engine  **[PROVEN on synthetic signals]**

Code: class `Predictive` in `reference/tp_ref.py`. Port it line by line.

#### 5.6.1 Idea

- Use a long window only to **measure** each steady partial: frequency, level, phase.
- **Predict** those partials a few samples into the future as plain sine waves.
- Subtract the prediction from the incoming audio. What is left (attacks, noise, new notes, anything not predicted) is the residual.
- The residual goes through the varispeed of section 5.2.
- The predicted partials are played again at the shifted frequency, each with its own phase turn Θ (section 5.1).
- Output = shifted sines + varispeed of the residual.

Nothing is lost by construction: if the prediction is wrong, the error is in the residual and is still shifted correctly by the varispeed. A bad prediction only costs quality, never notes.

#### 5.6.2 Steps per hop (H = 32 samples)

1. **Audio.** For the next H samples: `residual = x − g · predicted_original`, `out = g · predicted_shifted + varispeed(residual)`. `g` is the fit gate (step 7). The prediction for these samples was made in earlier hops, so this step needs no look-ahead.
2. **Measure.** Take the last 8192 samples. Window: smooth rise over 6144 samples, smooth fall over 2048, zero at both ends. FFT with 4× zero padding.
3. **Peaks.** A peak must be the largest value within 3 bins (of the 8192 grid) on each side. This also rejects side lobes of strong neighbours. Thresholds as in 5.3.2.
4. **Frequency** of each peak from the phase change since the last hop. **Complex amplitude** from the peak value, with the window's centre delay removed (`c = X[pk] · exp(−j·2π·u·n0/N4) / sum(window)`).
5. **Tracks.** Match each peak to the nearest old track within 1.5 bins. A track carries: Θ, mask, slow level, slow frequency.
6. **Mask** per track (0 = leave it to the varispeed, 1 = predict it): the stability mask of 5.4.1, times a "frequency is steady" factor. New tracks start at 0.
   **Θ** per track: new track `Θ = −ω · (d_A + r − 1)`; else `Θ += (r − 1) · ω_avg · H`. After a jump of the varispeed, tracks with mask < 0.5 get the new-track value again.
7. **Fit gate** `g`: over the last 12 hops (8 ms), `fit = sum(x · predicted_original) / sum(predicted_original²)`. Below 0.35 the prediction is switched off, above 0.75 fully on, smooth in between, ramped inside each hop. This catches muted strings.
8. **Predict** 2H samples ahead for each track: level = measured level × mask × decay correction (the measurement is about 60 ms old; follow the level trend to now). Two sums of cosines: one at the original frequencies (for the subtraction), one at `r ×` frequency with Θ added (for the output). Cross-fade with the prediction of the last hop.

#### 5.6.3 Measured (synthetic, 48 kHz)

See `docs/RESULTS.md`. Short version: chord wobble 0.3–0.6 dB (varispeed alone 3.5–7.2 dB), chord pitch error 0.1–0.2 cents (varispeed up to 9.6), single notes as good as varispeed, attack 2 ms.

#### 5.6.4 Notes for the C++ port

- The reference uses a 32768-point FFT every 32 samples. That is far too heavy. Use an 8192-point FFT with no padding, find the peak position by a parabola through 3 log-magnitude points, and correct the phase with the window's known centre delay. Check against the reference numbers.
- The measuring does not have to run every 32 samples. Try every 64 or 128 and predict further ahead. Measure the cost in wobble before deciding.
- The sum of cosines is up to 150 partials × 2 × 48000 samples per second. Use recursive oscillators or SIMD.
- The measuring can run on the audio thread (fixed cost per hop). Do not move it to another thread in the first version.
- Keep the same parameter names as `Params` in `tp_ref.py`.

#### 5.6.5 Open problems, most important first

1. **Vibrato and bends** (spec 0.91 against 0.44 for varispeed alone). The engine predicts a moving partial badly. The current "frequency is steady" test compares the frequency with its own 20 ms average. A strict setting helps vibrato but drops good partials in chords; a loose one does the opposite. Ideas: use the relative change (percent, not Hz); look at all harmonics of a note together (in vibrato they all move by the same percent); add hysteresis so a track does not flip in and out.
2. **Palm mutes and re-picked notes** (spec 0.75 against 0.58). A string that is picked again keeps its frequency but jumps in phase. The old track goes on predicting the old phase for a while. Idea: at every detected onset, drop the mask of tracks whose level jumped up.
3. **A new note over ringing notes** ("strum + late note": one partial wobbles 7.7 dB). Find which partial and why. Likely a ringing partial close to a partial of the new note.
4. **Only one string muted while others ring.** The fit gate is global, so it cannot see this. Needs a per-partial check. Not measured yet; add a test first.
5. **Partials a few Hz apart** (common in chords). The window cannot split them and one sine cannot follow their beating 60 ms ahead. The wobble measure skips them, so their quality is unknown. Add a measure for them (for example, compare the level curve of the pair against the target with a time stretch of 1/r).
6. **Level after distortion.** "dist" is a little worse for M than for A in several scenarios even where "spec" is better. Find out what the distortion reveals.

### 5.7 Lessons from the rejected bin-moving engine

Keep these in mind for Studio mode and for anyone who wants to try a spectral Live engine again.

- **Why it failed.** With a short output window (S = 128), the analysis window must fall to zero within 64 samples at the newest end. That sharp edge carries the "what is happening right now" part of every partial, and in the spectrum a sharp edge is wide: about ±750 Hz. Guitar partials are 82–330 Hz apart, so each partial's "now" lies under its neighbours and is turned with the wrong partial. With S = 512 the wobble on a 220 Hz note is gone, but then the delay is 10.7 ms and the low E still fails. This is the same wall the 2021 thesis hit; the lopsided window does not get around it when bins are moved.
- **Mirror image.** A real tone has a mirror image at negative frequency. With a short output window the mirror image leaks far into the positive bins of low notes. It must be turned the opposite way (conjugate rotation, shift by −s). Without this a 220 Hz tone had side tones at −8 dB; with it −95 dB. The reference splits tone and mirror image with two frames a short time apart. That split has blind spots at multiples of fs/(2H) (750 Hz steps), where both frames say the same thing.
- **First-order fix for the fractional bin shift** (ramped window) works: side tones −78.6 → −95.5 dB.
- **Falling edge shape.** A half-Hann fall (power 2) is much better than a half-sine fall (power 1) for low tones.
- **Splices.** Pick true peaks of the match curve and refine to sub-sample. Otherwise each splice is a little early and the pitch goes flat.

---

### 5.8 Offline "Perfect" mode  **[USER REQUEST 2026-11-13 — first experiment done, engine not designed in detail]**

The user wants a mode made purely for quality. It may take minutes. It is a post-processing tool for recorded DI tracks, and it should transpose "nearly perfectly".

#### 5.8.1 Shape

- It cannot be a mode of the live plugin slot: a host gives a plugin small blocks and wants each one back at once.
- First version: **file in, file out.** A command-line tool (`tools/render`) and a page in the Standalone app: drop a WAV, choose semitones, render, get a WAV. In Ableton: export or freeze the DI clip, render it, drag the result back.
- Possible later version: a "capture" mode in the plugin (it records the track while Ableton plays it once, renders in the background, then plays the rendered audio in sync). More comfortable, much more work. Ableton has no ARA support, so the Melodyne-style direct access is not possible.

#### 5.8.2 What the first experiment showed

`Predictive(lookahead=True)` in the reference centres the 8192-sample measuring window on "now" (it sees 85 ms of future). Run with `python run_tests.py scen look` (engine L). Numbers in `docs/RESULTS.md`.

- Chord wobble 0.07–0.26 dB (Live engine 0.34–0.63, varispeed 3.5–7.2).
- "Strum + late note" worst partial 0.52 dB (Live engine 7.68).
- Hand-mute leftover −14.2 dB (Live engine −7.7).
- **New fault: pre-echo.** The engine sees a note before it starts and plays its partials a few ms early. Single-note "spec" gets worse (0.42 against 0.28).
- Vibrato better (0.67 against 0.91) but still behind varispeed (0.44).

This same look-ahead engine, with 85 ms latency, is also a candidate to replace Signalsmith as the **Studio** engine of the plugin. Decide in M6 by measurement and listening.

#### 5.8.3 Design ideas for the real offline engine (to be tested one by one in the Python reference)

Offline, everything is known in advance. Use that:

1. **Partial tracks with exact start and end.** Track partials over the whole file, forward and backward. Tie each track's start to the detected attack of its note, so nothing sounds before the attack. Tie its end to where it really ends.
2. **Measured envelopes, no prediction.** Level and phase of each partial are measured at every point in time and interpolated (the classic sinusoidal model of McAulay & Quatieri / Serra). No decay guess, no fit gate.
3. **Several window sizes.** Long windows (8192 and more) for steady low partials, short ones for moving partials (vibrato, bends) and for high partials. Choose per track by how fast its frequency moves.
4. **Peel in rounds.** Subtract the strongest partials, measure the rest again, repeat. This separates partials that sit close together (the beating pairs of section 5.6.5 item 5).
5. **Residual by varispeed with planned splices.** The residual (attacks, noise) is still shifted by varispeed, because varispeed is exact. But the splice points are now chosen over the whole file: at attacks and in quiet spots, with an unlimited search for the best match.
6. **Check itself.** After rendering, measure the output against the model (pitch, level curves) and render again where it is off.

Goal for "nearly perfect" on the synthetic set: every scenario at or below varispeed's single-note numbers (spec ≤ 0.35, wobble ≤ 0.1 dB, pitch ≤ 0.1 cents), including chords, vibrato and palm mutes. Then the user's ears on real recordings, against the real down-tuned takes of section 7.2.

Risk: this is research. Items 1–3 are known methods and should work. Items 4–6 are bets.

#### 5.8.4 What was built (2026-11-13), in `reference/tp_offline.py`

Class `Offline`. Numbers in `docs/RESULTS.md`. Run: `python run_tests.py scen off`. Listen: `python render.py in.wav out.wav -2 O`.

1. **Tracks.** Centred 8192-sample window, 4× zero padding, hop 128. Peaks linked into tracks. Each track gets its own fit window W = 3 periods of the gap to its nearest real neighbour (512 … 8192). Only neighbours within 30 dB count; weaker peaks are mostly window side lobes.
2. **Picks and stops.** Picks by spectral flux (`detect_attacks`), placed exactly by `attack_start`. Sudden stops by `detect_stops` (power falls under 3 % of what it was 40 ms earlier, with a 20 ms power window so a low string does not fool it). Together these are the "cuts".
3. **Fit in rounds** (5 rounds, step 0.8). Each track's complex level curve A(t) is fitted against what is left of the audio, then subtracted. Fit windows never reach across a cut.
4. **Join.** After round 2, a track drops a cut if one or two undisturbed decaying sines explain its curve across the cut (±60 ms, model error < 0.15). That is a ring-through, or the dip of a beat. Otherwise the cut stays (new pick, also of the same string at the same level; stop; new partial added). A level-only rule failed: it took palm-mute re-picks for ring-throughs.
5. **Beat split.** Where a track holds two or three partials a few Hz apart (one track, a beating curve), the matrix pencil method splits the curve into decaying sines, measured against a fixed frequency. Each one's frequency offset is scaled by r, so the beat slows down by r, like on a real down-tuned guitar. Used only where the sines explain the curve to within 10 %, so vibrato is left alone.
6. **Render.** Each track: |shifted curve| × cos(r × track phase + phase of shifted curve + constant). The constant: for a stretch that starts at a pick, every partial of that pick uses the pick itself as the phase reference (measured a little after the pick and stepped back with the partial's own frequency). This keeps the partials of one note in line with each other. Before this rule, a single note at +2 scored 0.25; after it, 0.04.
7. **Ring-on** (at another string's pick, a partial that was already ringing is split into the old part, carried on with its decay and old phase, and the new part). Built and switched on, but it fires rarely and showed no measurable gain yet.
8. **Residual** through the varispeed, re-synced 192 samples before each pick and aimed so the delay is exactly `rest` when the pick arrives.

Tried and switched off: **birth picks** (`use_births`, find the pick at which each partial starts with two long windows around each pick). With symmetric windows it found the pick one too late; with lopsided windows it missed it. No gain either way.

#### 5.8.5 Open problems, most important first

1. **Attack detector.** It finds 28 of 46 picks in the test set, with 7 false ones. With the true picks, palm mutes go from 0.41 to 0.30 and the same-string run from 0.36 to 0.30. This is now the cheapest big gain. Ideas: use the tracks themselves (many partials restarting at once = a pick); combine flux with the phase jump of the strongest partials; tune on real recordings.
2. **Vibrato** (0.39; varispeed alone 0.44, so already a little better). The tracking window (8192) smooths a 5 Hz vibrato away, so the vibrato lives in the phase of the level curve, and short fit windows are needed to follow it. Try: a shorter tracking window for tracks whose frequency moves; or fit the vibrato as a frequency curve per note (all harmonics move by the same percent).
3. **Fast strum** (0.63). The long-window measure is good (0.19), so levels and frequencies are right. What is off is the phase between partials of different strings, plus some partials that take a neighbouring string's pick as their reference. The first part is likely not audible (partials of different strings are not harmonically related). The second may slightly change each string's waveform. Needs a listening test before more work.
4. **Speed.** 15 s per second of chord in Python. Port to C++ when the numbers are final.
5. **Turn the two-sine beat test into a unit test** in `run_tests.py`.

---

## 6. Timbre fix (pickup resonance)  **[BET #3, small]**

A pickup with its cable forms a resonant low-pass filter (peak at 2–5 kHz).
On a real down-tuned guitar this peak stays where it is. A shifter moves it down by ratio r. The result sounds dull.

Fix: one biquad filter after the shifter.
- Model the pickup as a 2nd-order low-pass with frequency `f0` and `Q` (start: 3.5 kHz, Q = 2).
- Correction = (pickup model at `f0`) ÷ (pickup model at `f0·r`). As a biquad: zeros at the poles of the model at `f0·r`, poles at the poles of the model at `f0`, same Q. Gain 1 at DC.
- "Timbre" knob blends from flat (0 %) to full correction (100 %). Cap the boost at +9 dB.
- Zero added latency.

Gate: the user compares shifted standard-tuning takes with the real down-tuned takes (section 7). The Timbre setting that sounds closest becomes the default. If no setting helps, leave the knob at 0 % and hide it under "Advanced".

### 6.1 Calibrate (optional, build only if the gate above shows the timbre fix matters)

Idea from the user: play for a short time in the pickup switch position you are going to use, and let the plugin tune itself to it.

Why it helps: each switch position (neck, middle, bridge) has its own resonance peak. One fixed guess for `f0` and `Q` cannot fit all of them.

How it works:
- The user presses "Calibrate" and plays about 30 seconds: single notes across the whole neck, a few chords, then a few seconds with hands off the strings.
- The plugin averages the spectrum of the played part (long-term average, smoothed over frequency) and fits the pickup model: `f0` and `Q`.
- From the hands-off part it measures the noise floor. Use it to set the onset detector's absolute threshold and the idle re-sync threshold (section 5.2).
- From the played part it measures the typical level. Use it to scale the onset detector.
- Results are saved as a profile. Three profile slots (1, 2, 3), one per switch position. The user selects the slot by hand, because the plugin cannot see the switch. Profiles are saved with the plugin state.
- The analysis runs off the audio thread. The audio thread only copies samples into a pre-allocated buffer.

What it does not change: latency and chord quality. Those come from the engine and are the same for every guitar.

Do not try to detect the switch position from the sound in the first version. A wrong guess would change the tone in the middle of playing.

---

## 7. What the user needs to provide

### 7.1 DI recordings (the test set)

Format: 48 kHz, 24-bit, mono WAV, straight from the interface. No plugins. Peaks near −12 dBFS. One item per file. Put them in `audio/di/standard/`.

1. Single notes: every open string, plus frets 5 and 12 on each. Let each ring 5 seconds. On the 7-string, include the low B and a low-B power chord.
2. Palm-muted 16th notes on the low E at 120, 160 and 200 bpm.
3. Power chords (E5, A5, D5): let ring, and short stabs.
4. Open chords (E, Am, C, G, D) and barre chords: slow strum, fast strum.
5. Arpeggios, let ring.
6. Bends, vibrato, slides, hammer-on / pull-off runs, tapping.
7. Fast alternate picking and tremolo picking.
8. Natural harmonics (frets 5, 7, 12) and pinch harmonics.
9. Unison bends and double stops.
10. 10 seconds of "silence" (hands off), muted strums, pick scrapes.
11. Three real parts, 30–60 seconds each: a heavy rhythm riff, a lead, a clean part.

### 7.2 Real down-tuned takes (the realism reference)

Retune the guitar for real and record items 1–5 and 11 again in: E♭ standard (−1), D standard (−2), C standard (−4). Put them in `audio/di/tuned_-1/` and so on.
They will not line up sample by sample with the standard takes. That is fine. They are for listening tests and for the timbre fix.

### 7.3 Competitor renders

Run the files from 7.1 through each competitor at −1, −2, −5 (HyperTune demo, any pedal you own, your amp-sim's transpose) and save the output to `audio/competitors/<name>/`. The harness scores them next to ours.

### 7.4 Listening

At each milestone the harness writes a blind test folder (random file names plus a hidden key). The user listens through their usual amp sim, clean and high gain, and picks the best.

---

## 8. Test harness (this is how a coding model can tune without ears)

### 8.1 Pieces

- `tools/render`: command-line program. `render --engine <name> --semitones <x> in.wav out.wav`. Uses the same core library as the plugin. Processes in blocks of 64 samples to act like a DAW.
- `tools/eval/*.py`: Python + NumPy only. A small own WAV reader/writer (`wavio.py`, PCM16/24 and float32). Metrics and a results table.
- `tools/gen/*.py`: makes the synthetic test signals of 8.2.
- `tests/`: unit tests in C++ (Catch2).

### 8.2 Synthetic signals with a known perfect answer

A simple additive guitar model. For each note:
- Partials at `f_k = k·f0·sqrt(1 + B·k²)`, B from 0.00005 to 0.0005 (string stiffness).
- Start level of partial k: `(1/k) · |sin(k·π·p)|` with pluck point p from 0.1 to 0.25.
- Each partial decays exponentially. Decay time shrinks with frequency (for example 3 s at 100 Hz to 0.3 s at 5 kHz).
- Attack: a 5–10 ms burst of band-passed noise.
- Whole thing through a pickup low-pass (3.5 kHz, Q = 2).
- Options: vibrato, bend, strum (notes start 5–20 ms apart), palm mute (all decays × 0.1).

Render each item twice with the same random seed: at pitch P (the input) and at pitch P shifted by the test amount (the target). Same timing, same levels. That target is the perfect answer.
Make two target kinds: "pure shift" (pickup filter moves with the pitch; this is what a perfect shifter with Timbre = 0 gives) and "real detune" (pickup filter stays; used for the Timbre gate).

Items: single notes across the range; E2+B2 power chord; open E chord; 6-note barre chord; slow strum; palm-mute train at 200 bpm; bend; vibrato; let-ring arpeggio. Shifts: −1, −2, −5, −7, −12, +2, +5.

### 8.3 Metrics

Align output and target first (shift by the engine's reported latency).

1. **Spectral distance**: mean absolute log-magnitude difference over STFTs of sizes 256, 1024 and 4096. Lower is better. Main score.
2. **Pitch error**: per steady partial, in cents.
3. **Wobble (AM)**: per steady partial, RMS of its level around its smoothed level, in dB. This is the number that catches chord warble.
4. **Attack latency**: time from the target's onset (envelope crossing 10 % of its peak) to the output's onset. In ms.
5. **Attack sharpness**: ratio of energy in the first 10 ms after onset, output vs target. In dB.
6. **Pre-echo**: energy in the 10 ms before the target's onset, relative to the target.
7. **Sine purity**: the 997 Hz sideband test of 5.3.3.
8. **After distortion**: run output and target through `tanh(30·x)` followed by a 5 kHz low-pass, then compute metric 1 again. This shows what a high-gain amp will reveal.
9. **CPU**: seconds of processing per second of audio.
10. **Measured latency**: impulse in, find the peak out. Must equal the reported latency.

For real DI files there is no target: use metrics 3, 4, 9 and listening.

Warning: these numbers are a guide, not the judge. Earlier work (section 3.2.1) found that numbers miss some artifacts, mainly loss of phase coherence. A change that improves the score but sounds worse to the user is a bad change. The user's blind listening test decides every gate.

Total score per item = weighted sum of 1, 3, 5 and 8 (start with equal weights after scaling each to the baseline's range). Record every run in `docs/RESULTS.md`.

### 8.4 Unit tests (minimum)

- STFT with no edit returns the input, delayed by S, error < −100 dB.
- Every engine with r = 1 returns the input (delayed) within −80 dB.
- Reported latency equals measured latency for every engine and mode.
- No NaN or Inf on silence, full-scale noise, DC, and a full-scale square wave.
- Same output for host block sizes 16, 64, 512 and 1024 (bit-exact or within −120 dB).
- Sample rates 44.1, 48, 88.2, 96 kHz all run and pass the r = 1 test.
- `processBlock` does not allocate (use a debug allocator hook in the test build).

---

## 9. Machine learning: honest assessment

### 9.1 Why amp modelling is easy and this is not

| | Amp model (Neural DSP, NAM) | Pitch shifter |
|---|---|---|
| Training pairs | Free: play any signal through the amp and record | None: no two takes are identical in two tunings |
| What the net must do | Reshape the wave it is given (short memory) | Create new waves at new frequencies, with exact phase, for many notes at once |
| If the net is slightly off | Slightly different tone | Wrong notes, noise, warble — then made louder by the amp |
| Proven real-time at < 5 ms | Yes | No. Best public result (BRAVE, 2025) is < 10 ms for timbre transfer, which is not transparent |

### 9.2 How training data could be made anyway

1. Synthetic pairs from the model in 8.2 (endless, exact, but only as real as the model).
2. Teacher–student: an offline shifter with long look-ahead makes the targets; a causal network learns to match it with less delay. The student can never beat the teacher.
3. Per-string recordings (a hex pickup; the public GuitarSet data has this for acoustic guitar): shift each string alone with a clean single-note method, then sum. Gives nearly clean chord targets.
4. Unpaired real takes in two tunings (section 7.2) with an adversarial loss. Hard to train, risky.

### 9.3 Where a small network could really help (research track, after M5)

Replace the hand-made mask of 5.4.1 with a tiny causal network (a few thousand weights, runs once per hop on spectral features). It only decides "tonal or residual" per region. It never makes audio. So it cannot add noise or phase errors, and it costs almost no CPU.
Training data: the synthetic set of 8.2, where the true tonal/residual split is known, plus the user's recordings for checking.
Run it with RTNeural or plain hand-written C++ loops.

Gate to start this: after M5, the remaining errors are mostly wrong mask decisions (check by feeding the Hybrid the true mask on synthetic data; if the score jumps, a better mask is worth it).

### 9.4 Not recommended now

A full neural shifter (network outputs the waveform). Revisit only if the Hybrid has a quality problem that no DSP change fixes.

---

## 10. Tech stack and licenses

| Part | Choice | License | Note |
|------|--------|---------|------|
| Plugin framework | JUCE, exact tag (9.0.2 was the newest seen on 2026-11-12; check and pin) | Free "Starter" tier under a yearly revenue limit (reported as $20k; read the current EULA), else paid | CMake build, no Projucer |
| VST3 SDK | The one bundled with the pinned JUCE | MIT since 3.8 | |
| Build | CMake + Visual Studio 18 (installed). CMake is not on PATH; use the one bundled with Visual Studio or ask the user to install it | | |
| FFT | PFFFT (marton78 fork), pinned commit | BSD-like | Core library must not depend on JUCE |
| Baseline / Studio engine | Signalsmith Stretch, pinned tag | MIT | |
| Harness-only baselines | Bungee (MPL-2.0), SoundTouch (LGPL-2.1) | | Linked only into `tools/render`, never into the plugin |
| Rubber Band | Its own command-line program, run on WAV files | GPL | Never link it |
| Unit tests | Catch2 v3, pinned tag | BSL-1.0 | |
| Plugin validation | pluginval (Tracktion), pinned release | GPL, used only as a tool | Strictness level 10 |
| Analysis scripts | Python 3.14 + NumPy (installed) | | |

Fetch dependencies with CMake `FetchContent` using `GIT_TAG <exact tag or hash>`. List each one with its version in `docs/DEPENDENCIES.md`.

Patents: there are patents on filter-bank pitch shifters (for example US 12,689,866 "Filterbank pitchshifter") and older ones on phase-vocoder tricks. This plan does not copy any of them on purpose, but nobody here has checked. **Before selling the plugin, the user should get a patent check.** This is not legal advice.

---

## 11. Folder layout

```
PLAN.md
CMakeLists.txt
core/                 static library "tp_core". Plain C++20. No JUCE.
  include/tp/         public headers (Engine interface, parameters)
  src/                DelayLine, Interpolator, OnsetDetector, EngineA,
                      LowDelayStft, PeakTracker, EngineB, TonalMask, Hybrid, TimbreEq
plugin/               JUCE wrapper: PluginProcessor, PluginEditor, parameters
tools/render/         command-line renderer (uses tp_core + baselines)
tools/gen/            synthetic signal generator (Python)
tools/eval/           metrics (Python)
tests/                Catch2 tests
audio/                test audio (large files stay out of git)
docs/                 RESULTS.md, DECISIONS.md, DEPENDENCIES.md
```

Engine interface (all engines implement it, so they can be swapped by one setting):

```cpp
struct Engine {
    virtual void prepare(double sampleRate, int maxBlockSize, int numChannels) = 0;
    virtual void setRatio(double r) = 0;            // smoothed inside
    virtual int  latencySamples() const = 0;        // for the current ratio sign
    virtual void process(const float* const* in, float* const* out, int numSamples) = 0;
    virtual void reset() = 0;
    virtual ~Engine() = default;
};
```

Real-time rules for all code called from `process`:
- No memory allocation, no locks, no file or console output.
- Fixed inner hop, independent of the host block size (use input and output FIFOs).
- Turn off denormals (`juce::ScopedNoDenormals` in the plugin; `_mm_setcsr` flags in the core).
- Smooth every parameter change (ratio: 20 ms ramp).

---

## 12. Milestones

Each milestone ends with: results in `docs/RESULTS.md`, a short report to the user, and a question before going on.

### M0 — Setup  **[DONE 2026-11-12, except loading in Ableton]**
- Ask the user, then `git init`. Add `.gitignore` (build folders, `audio/` large files).
- CMake project that builds an empty JUCE plugin (VST3 + Standalone) and the empty `tp_core` library.
- Pin all dependencies. Write `docs/DEPENDENCIES.md`.
- **Done when:** the plugin builds, loads in the user's DAW, passes audio through, and passes pluginval at level 10.
- Status: builds with no warnings (`scripts\build.bat`), passes pluginval level 10 (`scripts\pluginval.bat`). Not yet loaded in Ableton by the user. Nothing is committed yet.
- Build output: `build\Release\plugin\TransposePlugin_artefacts\Release\VST3\Guitar Transpose.vst3`. Ableton only scans `C:\Program Files\Common Files\VST3` for VST3 plugins; copying there needs admin rights (ask the user).
- Plugin name "Guitar Transpose", company "KU Audio", codes `Kuzu` / `Gtrp` are placeholders. Final names must be chosen before the user saves real Ableton projects with the plugin (see `plugin/CMakeLists.txt`).

### M1 — Plugin shell + baseline engine
- Parameters from section 4 (Timbre can be a dead knob for now; mark it in the UI).
- Engine interface. `SignalsmithEngine` wrapper as the Studio engine.
- Latency reporting. Delayed dry path for Mix. True pass-through at 0 semitones.
- Plain generic UI (JUCE sliders). No design work yet.
- Measure the output level of Signalsmith against the input at several shifts (a 2025 paper reports uneven level loss, section 3.2.2). Correct with a fixed gain per shift if it is off by more than 0.5 dB.
- **Done when:** the user can transpose a recorded DI track in the DAW with Studio mode, in time with other tracks. Measured latency = reported latency.
- Status 2026-11-13: **code done, waiting for the user's Ableton test.**
  - Parameters: Transpose, Fine, Mode, Mix, Output (IDs `transpose`, `fine`, `mode`, `mix`, `output`, version 1; never rename them). Timbre and Pickup Freq are left out until M6.
  - Studio = Signalsmith default preset, 5760 samples (120 ms at 48 kHz). Live = Signalsmith with 40 ms blocks, 1920 samples (40 ms). **Live is a stand-in until M3.**
  - Reported = measured latency for both (unit test, noise cross-correlation 1.000).
  - Signalsmith level error is at most ±0.31 dB over −12 … +12 st and 110 / 440 / 1500 Hz. No gain correction needed.
  - At 0 st and 0 cents the plugin outputs the dry signal delayed by the same latency (20 ms crossfade).
  - Unit tests: `scripts\test.bat`. pluginval level 10 passes.
  - Bug found and fixed: Signalsmith divides by zero if `reset()` runs before `configure()`. Hosts call `releaseResources()` before the first `prepareToPlay()`. The wrapper now ignores calls until it is configured. Keep this rule for every engine.

### M2 — Test harness
- Already done in Python: the signal generator, the metrics and the test runner are in `reference/` (`synth.py`, `metrics.py`, `run_tests.py`). Reuse them; do not write them again. Left to do: the C++ `tools/render` program, a way to score its output with the Python metrics, and the baselines.
- `tools/render`, `tools/gen`, `tools/eval`, unit-test skeleton.
- Baselines wired in: Signalsmith, Bungee, SoundTouch. Rubber Band via its own program if the user installs it.
- **Done when:** one command renders the full synthetic set through every baseline and prints the score table. Table saved in `docs/RESULTS.md`. This table is the bar to beat.

### M2.5 — Listen to the reference on real guitar (can be done today, needs no compiler)
- The user records a few DI files (section 7.1; start with items 2, 3, 4 and 6).
- Render each one at −2 and −5 with `python render.py in.wav out.wav -2` (engine M) and with `... -2 A` (varispeed only).
- The user listens through their amp sim, clean and high gain, and says which is better and what sounds wrong.
- **Done when:** the user's notes are in `docs/RESULTS.md`. If M does not beat A on real chords, stop and find out why before writing any C++.

### M3 — Port the varispeed (Engine A) to C++
- Port `Varispeed`, `detect_onsets` and `engine_a` from `reference/tp_ref.py`. Put it in the plugin as a first Live mode.
- The reference does a full-rate splice search. In C++ search on a 4× decimated copy first, then refine.
- **Done when:** the C++ output matches the reference output on the test signals within −80 dB; reported latency = measured latency; no allocation in `process`. The user plays through it and reports the feel.

### M4 — Port the predictive engine to C++
- Port `Predictive` (section 5.6), with the changes of 5.6.4 for speed.
- **Done when:** on every scenario of `run_tests.py` the C++ wobble and spec numbers are within 10 % of the reference numbers in `docs/RESULTS.md`, and CPU is under 15 % of one core (the speed work comes in M7).

### M5 — Fix the open problems
- Work through 5.6.5 in order. Do each fix in the Python reference first, measure, then port. Change one thing at a time. Log each change and its score.
- Add the missing tests named in 5.6.5 (one string muted; partials a few Hz apart).
- **Done when:** vibrato and palm-mute scores are within 20 % of varispeed alone, chord wobble is still under 0.7 dB, and the user's blind test against the HyperTune demo is done.

### M6 — Timbre fix and Studio decision
- Build section 6. Run its gate with the real down-tuned takes.
- Test Hybrid-with-look-ahead against Signalsmith for Studio mode (5.5). Keep the winner.
- **Done when:** defaults are chosen by listening tests and written in `docs/DECISIONS.md`.

### M7 — Speed and hardening
- Profile. Likely wins: inverse FFT of only the last S samples (direct sum over active bins), H = 64, SIMD in the interpolator, decimated correlation search.
- All sample rates and block sizes. Stereo linking. 7-string low B and drop A tests.
- Automation of Transpose without clicks. State save and load. pluginval level 10. Test in the user's DAW plus at least one more host (Reaper is free to try).
- **Done when:** CPU < 5 % of one core at 48 kHz / 64-sample blocks; no failing test.

### M8 — UI and release
- Real UI (ask the user for the look first). Installer. Manual page with latency numbers.

### M9 — Offline "Perfect" mode (section 5.8)
- Can start any time after M2.5; it does not depend on the C++ port. All research happens in the Python reference first.
- Step 1: fix the pre-echo of the look-ahead engine (tie track starts to attacks). Step 2: several window sizes for vibrato. Step 3: planned residual splices. Then the bets (peeling in rounds, self-check).
- Port to C++ as a file-in, file-out tool only when the Python numbers reach the goal of 5.8.3.
- **Done when:** the goal of 5.8.3 is met on the synthetic set, and the user prefers the offline render over Studio mode and over the HyperTune demo in a blind test on their own recordings.
- Status 2026-11-13: steps 1 and 2 of the list above are done, plus the beat split and the common phase reference per pick (5.8.4). 12 of 16 scenarios meet the goal. Open problems in 5.8.5. **Next: the user listens to `render.py ... O` on real DI recordings.**

### Research track (only after M5, each one needs the user's OK)
- R1: learned mask (9.3).
- R2: per-string view for chords: group peaks into notes (harmonic series) so that all partials of one note share one delay. This keeps each note's wave shape, which matters for how distortion reacts.
- R3: "Calibrate" per pickup switch position (section 6.1).
- R4: full neural shifter (9.4). Not recommended.

---

## 13. Risks

| Risk | Sign | Answer |
|------|------|--------|
| Short synthesis window makes the tonal path rough | Sine purity test fails; buzz at the hop rate | First-order fix in 5.3.3; then larger S; then Bet #1 fallback |
| Mask flips back and forth | Partials wobble at a few Hz; AM metric gets worse than Engine B alone | Longer smoothing; hysteresis (rise at 0.8, fall at 0.5); then R1 |
| Past-only mask splits badly (this is what hurt the 2025 paper in 3.2.2) | Hybrid scores below Engine A or B; "true mask" check shows a large gap | 1–2 frames of look-ahead (0.7–1.3 ms more latency); then R1 |
| Low chords still not resolved | E2+B2 pitch test fails | N = 8192 for bins under 300 Hz (second STFT, low bins only) |
| Onset detector misses soft attacks | Legato notes start late | Idle re-sync (5.2 b) already covers most; add spectral-flux detector |
| Onset detector fires on ringing chords | Clicks on sustained chords | Re-sync only moves the residual path, which is quiet then; raise threshold |
| Up-shifts sound worse than down-shifts | Flam on attacks at +5 and more | Larger runway `R_up` (more latency); tell the user this is physics |
| CPU too high with N = 4096, H = 32 | > 10 % of a core | H = 64; partial inverse FFT; see M7 |
| Whole Hybrid idea fails | Gate #2 fails twice | Fallbacks in 5.4; Engine A + Signalsmith is still a usable product |

---

## 14. Open questions for the user (defaults are used until answered)

1. DAW: **answered — Ableton Live, VST3.**
2. Is this for you only, or do you want to sell it? (Default: assume it may be sold, so no GPL code and a patent check before release.)
3. Range: **answered — 6- and 7-string. No 8-string, no bass.**
4. Do you want macOS later? (Default: keep the code portable, build Windows only.)

---

## 15. Reading list

- Laroche & Dolson, "New phase-vocoder techniques for pitch-shifting, harmonizing and other exotic effects" (1999). The peak / region idea of 5.3.
- Mauler & Martin, "A low delay, variable resolution, perfect reconstruction spectral analysis-synthesis system for speech enhancement" (EUSIPCO 2007). The window pair of 5.3.1.
- Juillerat, Müller Arisona, Schubiger-Banz, "Low latency audio pitch shifting in the time domain" (2008). The "Rollers" filter-bank method.
- Juillerat & Hirsbrunner, "Low latency audio pitch shifting in the frequency domain" (2010). 12 ms STFT method.
- Fierro & Välimäki, "Enhanced Fuzzy Decomposition of Sound Into Sines, Transients, and Noise" (JAES 2023, arXiv 2210.14041). The mask idea of 5.4.1.
- Průša & Holighaus, "Phase Vocoder Done Right" (arXiv 2202.07382). Phase handling without peak picking; an option if peak tracking proves fragile.
- Geraint Luff, "Four Ways To Write A Pitch-Shifter" (ADC 2022 talk) and the Signalsmith Stretch source.
- Patrick Nolte, "Latenzoptimierte Tonhöhenverschiebung polyphoner Gitarrensignale" (master's thesis, HAW Hamburg, 2021, in German). Compares OLA, SOLA, WSOLA, Rollers, phase vocoder and constant-Q methods for exactly this problem. Its results are summed up in section 3.2.1. https://reposit.haw-hamburg.de/handle/20.500.12738/15713
- Caspe et al., "Designing Neural Synthesizers for Low-Latency Interaction" (BRAVE, arXiv 2503.11562). State of low-latency neural audio.
- Polak & Erkut, "Low-latency Pitch-Shifting with STN decomposition" (DAGA 2025). The closest published design; read its "Discussion" before M5. https://pub.dega-akustik.de/DAS-DAGA_2025/files/upload/paper/635.pdf
- Moliner et al., "Noise Morphing for Audio Time Stretching" (IEEE Signal Processing Letters 2024, arXiv 2312.14586).
- Geraint Luff, "The Design of Signalsmith Stretch" (2023). https://signalsmith-audio.co.uk/writing/2023/stretch-design
- Cycfi Research blog: "DSP Adventures: Zero Latency Pitch Shifting" (2026-06) and "BACF Pitch Shifter" (2026-11). https://www.cycfi.com/2026/11/bacf-pitch-shifter/
- Riou et al., "PESTO" (arXiv 2508.01488). Causal neural pitch detector.

---

## 16. Doubler and first release (user request 2026-11-23)  **[PYTHON REFERENCE DONE 2026-11-24 — waiting for the user to listen]**

Goal: make a real-sounding double or quad take of a guitar, not a fixed-delay copy (the Neural DSP way).
A real second take differs in **timing** (per note, early and late), **pitch** (a few cents per note),
**level and attack**, and **tone**. A fixed delay has none of these, and it comb-filters in mono.

### 16.1 User answers
- Placement: after the amp sim (input is already amped, often stereo).
- One plugin with two sections: Transpose → Doubler, each with on/off.
- Original stays in the output as take 1 (hard left). Copies are takes 2–4.
- Latency: the smallest the processing allows, and it is **not a parameter** (user, 2026-11-24). The doubler
  reports **12 samples** (0.25 ms): the fixed part every note has. The human timing on top is the effect itself,
  so it is not reported (user, 2026-11-24). Every take, **the original included**, lands from 0.25 ms (what the interpolator needs) up to the
  timing spread after the input, drawn anew per note. So the order of the takes is mixed note by note: no take
  is always first (user chose this "option B", 2026-11-24). The original gets timing changes only, no pitch,
  level or tone change. Every timing setting must have a **wide range**, and the amount of
  randomness must be adjustable, "just like a human".
- Visual: Stage (one glowing speaker per take at its pan spot, with live ms and cents) + Takes (scrolling
  waveform lane per take, note starts marked early/late) + a mono-safety strip.
- Look: same colours, fonts and knob style as `C:\guitar-lab`.
- Identity: company **"Kursat"** (Ableton groups by this), product **"Guitar Tools"**, manufacturer code `Kuzu`,
  new plugin code (never released before, so changing now is safe). Bundle id to match.
- Transpose ships as it is, marked "beta" (Live mode is still the Signalsmith stand-in, 40 ms).
- First release: **v0.1.0**, setup .exe + zip, installer like Guitar Lab (`C:\guitar-lab\installer\GuitarLab.iss`, Inno Setup).
  No GitHub Actions (user, 2026-11-26): a local PowerShell script builds (CMake), makes the setup .exe (`iscc`)
  and publishes it with `gh release create`. Ask the user before tagging, pushing or running it.

### 16.2 Engine (one per copy)
- A **varispeed delay line** (reuse `Varispeed` from `reference/tp_ref.py`): reading slightly faster or slower
  gives a pitch offset of a few cents with no FFT and no latency.
- At every clear pick (`detect_picks`: power above 1.5 kHz, 1 ms against 30 ms, ratio 4), each copy draws a
  **new timing, pitch, level and tone** and jumps there with a 64-sample crossfade, before the attack reaches it.
  `detect_onsets` from the transpose engine finds almost nothing after distortion (1 of 24 chug picks).
- Between picks, every ~300 ms (random 150–450), a copy moves to a new timing and pitch with a **matched splice**
  (jump by whole waveform periods, likeness ≥ 0.8, else it waits). So a missed pick costs nothing.
- When a long note drifts more than 5 ms from its timing, a matched splice brings it back
  (30 cents ≈ 17 ms drift per second).
- Timing = slow drift (random walk over notes: rushing/dragging) + per-note jitter.
- Per-pick level change and tone change (gain above 1.5 kHz). Both start when the pick reaches the copy's
  read head, not when it enters the plugin.
- A **velvet-noise filter** above 600 Hz on every copy (15 ms, 30 pulses, fixed per take). It scrambles the
  copy's fine detail, so two takes in one speaker stop cancelling at regular frequencies (see 16.6).
- Stereo input: copies on the left are made from the left channel, copies on the right from the right channel
  (keeps the two cabs' tone difference). Mono input: all from the one channel.
- Randomness is seeded (a "New takes" button changes the seed), so the same audio renders the same every time.
- The original is a take with timing changes only. Its sound is untouched: with timing spread 0 it is the
  input delayed by exactly 12 samples (tested). Every take's timing is folded to the late side (none can be early).

### 16.3 Parameters (start values; ranges are wide on purpose)
| Name | Range | Default |
|------|-------|---------|
| Doubler on | off/on | off |
| Takes | 2 / 3 / 4 | 2 |
| Timing spread | 0 … 40 ms | 8 ms |
| Timing jitter (how much it changes note to note) | 0 … 100 % | 60 % |
| Timing drift (slow rush/drag) | 0 … 100 % | 30 % |
| Pitch spread | 0 … 30 cents | 6 |
| Pitch jitter (per note) | 0 … 100 % | 60 % |
| Pitch wander (inside a note) | 0 … 10 cents | 1 |
| Level spread (per note) | 0 … 6 dB | 1 |
| Tone spread | 0 … 100 % | 30 % |
| Decorrelation (velvet filter on the copies) | 0 … 100 % | 100 % |
| Width | 0 … 100 % | 100 % |
| Copies level | −24 … +6 dB | 0 |
| New takes (seed) | button | — |

Takes layout: 2 = original L, copy R. 3 = + copy centre. 4 = original L, copy R, copy L and copy R at Width × 80 %.
No lean: the original is late as often as the copies, so no side is always first.

### 16.4 Order of work
1. **[DONE 2026-11-24]** Python reference `reference/tp_double.py`, tests `double_tests.py`, listening tool
   `render_double.py`. Results in 16.6. **Next: the user listens on real amped tracks.**
2. C++ `DoublerEngine` in tp_core + unit tests (safe before `prepare()`, no allocation in `process`,
   reported = measured latency).
3. Plugin: rename identity, parameters, sections, latency = transpose latency + x.
4. UI in the Guitar Lab look, with Stage + Takes view.
5. Installer + local release script + README/manual, v0.1.0. Ask before tag and push.

### 16.5 Open
- User asked what happens in Neural DSP with the two cab mics panned hard L/R and the Doubler on. Their manual
  says the Doubler only works in Mono input mode; how it treats the panned mics is not documented. Offer: user
  renders short clips (doubler off / on, mics centred / hard L-R) and we measure delay, pitch and correlation.

### 16.6 Results of the reference (2026-11-24)
Synthetic guitar with pick noise, through a simple amp (tanh + cab low-pass). Defaults of 16.3.
"coh" = how alike L and R are over time (1 = copy, 0 = unrelated). "mono" = L+R against L and R apart
(+3 dB = copies, comb filter in mono). Full table in `docs/RESULTS.md`.

| Part | Fixed 12 ms copy: coh mid / mono | Ours: coh mid / mono | True second take: coh mid / mono |
|------|------|------|------|
| Chug (palm-muted 16ths) | 0.78 / +2.8 dB | 0.06 / +0.6 dB | 0.03 / −0.2 dB |
| Power chords | 0.80 / +0.1 dB | 0.09 / +0.2 dB | 0.03 / −0.3 dB |
| Single-note lead | 0.78 / −0.7 dB | 0.22 / −0.6 dB | 0.19 / +0.5 dB |

The copy lands before the original on 50 % of chug picks (24), 25 % of chord picks (4) and 75 % of lead picks (12).

- **User listening (2026-11-24): quad sounds like a flanger / phaser.** Cause: every take is the same waveform,
  shifted. Two of them in one speaker cancel at *regular* frequencies (a comb), and the varying delay makes the
  comb move. Real takes have new fine detail (overtone phases, pick and string noise), so they cancel at random,
  changing spots. Coherence over time could not see this. New measure: "comb" = cepstrum peak of one channel
  against the input (0.3–30 ms).
- Comb in quad: ours 0.14–0.16, true quad 0.05–0.06. No pitch change: no better (the comb stops moving but
  stays). Timing 25 ms: 0.11–0.12. Doubling before the amp (amp per take): no better, because distorting a
  delayed signal is the same as delaying the distorted one. Band-split delays (4 bands, 0–2 / 0–5 ms): 0.08–0.10,
  peaks 3×. **Velvet filter at 1.0, 15 ms: 0.07–0.08, peaks about 2×** (8 ms: 0.08–0.09; 4 ms: 0.11).
- The velvet filter was first dropped because coherence did not move (a fixed filter keeps a fixed relation);
  it came back for the comb. It is on by default.
- Proof of idea (offline, 2026-11-24): each overtone of a copy gets its own slow phase drift (STFT 2048 / 256,
  random drift field smooth over 6 bins, about 1 Hz detune, nothing below 150 Hz). Quad comb 0.060 / 0.053 / 0.066
  = true quad (0.059 / 0.049 / 0.057). So new fine detail is the right fix. Peaks about 2.2×, like velvet.
- The same drift through the low-delay STFT (5.3.1, N 2048, S 128 or 256, 2.7 / 5.3 ms) is **not** better than
  velvet: 0.08 / 0.07 and lead 0.17 (S 128, worse than plain) or 0.11 (S 256). The short output window blurs the
  frequency detail.
- Left for low latency: the drift on the predictive engine's sine tracks (5.6): each track gets its own small
  detune, new at every pick, starting in line with the residual path. Big job and needs 5.6.5 problems solved
  on distorted input. Or a mixing mode with the full STFT drift (about 40 ms latency, compensated by Ableton).
- Open: lead picks are found 1 of 12 times (sustained high notes keep the highs busy). The matched splices carry it,
  but a better pick detector would make lead takes more real. Try first: ratio on the rise of the high-band level
  in dB, with a slower reference.
- Not tested yet: real amped recordings, stereo input with two different cabs, 44.1 / 96 kHz.

### 16.7 Studio mode (user request 2026-11-24)  **[PYTHON REFERENCE DONE — waiting for the user to listen]**
User: track in Live as one guitar, play back as a high-quality quad. In Studio, **latency is no concern, only the
quality of the algorithms**. Ableton removes the latency on playback (PDC).

- One shared Mode switch for the whole plugin (Live / Studio), as Transpose already has. Proposed to the user,
  not yet confirmed. When both sections are on, latencies add up.
- If the host renders offline (JUCE `isNonRealtime()`), use Studio even when Live is chosen. Not decided yet.
- Code: `reference/tp_double_studio.py`, tests `reference/studio_tests.py`, listening `render_double.py mode=studio`.
- Steps:
  1. **Pick finder with look-ahead** (`find_picks`): rise of the level above 1.5 kHz in dB plus spectral flux,
     each divided by its running median (±300 ms), summed. A pick is the highest within ±25 ms and more than 2.5
     above the running median. Found 24/24, 4/4, 12/12 (2 false in all); times up to 2.7 ms late.
  2. **Note-anchored timing** (`StudioTake`): the grid sits 50 ms back (`LOOKAHEAD_MS`), so takes land early or
     late around it, the original included. The jump to a note's timing ends 4 ms before the found pick, so the
     attack is never crossfaded. If the waveform lines up well (≥ 0.9) within 2 ms of the timing, it lands there
     (seamless); else exactly. No timing moves between picks.
  3. **Overtone drift** on the copies (`phase_drift`): STFT 2048 / 256, random drift rate per bin, smooth over 6
     bins, about 1 Hz, nothing below 150 Hz. Replaces the velvet filter. Its knob scales the speed; dry and
     drifted are never mixed (that would make a comb).
- Reported latency: 50 ms + one 2048 frame in real time (about 93 ms at 48 kHz).
- Results: quad comb 0.058 / 0.053 / 0.061 against true quad 0.059 / 0.049 / 0.057 (Live 0.071–0.074). Tight
  settings stay at 0.05–0.06 too. Timing spread between takes 4.1–4.8 ms. Full table in `docs/RESULTS.md`.
- Open: "copy first" was 33 % / 0 % / 42 % on parts of only 24 / 4 / 12 picks; check on a longer part.
  Extreme settings on the lead: comb 0.092. Real amped recordings not tested yet.
- **User listening (2026-11-24): still phaser-like, and the image leans left.** Measured: the copies' attacks
  were smeared (chug double: attack sharpness L 6.5 / R 1.6 dB, input 6.4) and the copies lost 1.0–2.3 dB in
  `phase_drift`. Cause: every bin drifted on its own, so the bins of one overtone drifted apart over a note.
  Fix (`phase_drift_notes`): (a) phase locking, every bin turns with its overtone peak; (b) each note processed
  on its own, drift starts at 0 just before the attack (attack untouched), new drift field per note; (c) attack
  detune: each overtone starts 15 cents off at random and settles over 40 ms, like a plucked string, so short
  notes get new detail too. After: balance −0.2 … +0.7 dB on doubles, copy attacks as sharp as the original,
  quad comb 0.068 / 0.063 / 0.077 (true quad 0.059 / 0.049 / 0.057).
- `studio_tests.py` now also measures balance (L−R dB) and attack sharpness per side.
- Ideas for later, if listening asks for more: drift tied to tracked overtones (peak-locked) instead of bins;
  a new drift field at every pick (a new "pluck"); borrowing the pick noise of another, similar note.

### 16.8 "Analyse and play again" on the DI (user choice 2026-11-24)  **[FIRST VERSION — waiting for the user to listen]**
User: Studio still sounds quite different from the true quad. Why: the true takes are made from the note list
(new overtone phases and new pick noise per take); the doubler only bends one recording, so it keeps its fine
detail. User chose: (1) analyse the recording and play each take again; (2) work on the **clean DI**, one take per
track: duplicate the DI track 2–4 times, set the plugin to Take 1 … Take 4 (same seed), each with its own amp sim.

- Code: `reference/tp_double_resynth.py` (`Resynth`, `ResynthDoubler`), tests `reference/resynth_tests.py`.
- Analysis = `tp_offline.Offline` at 0 semitones (picks, overtone tracks with fitted level curves, residual).
  Tracks explain the input: residual −24 to −26 dB of it.
- A take: every overtone keeps its level and frequency curve; every stretch that starts at a pick gets a random
  start phase (a new pluck). The residual gets random phases (STFT 256 / 64) and its old short-time level.
  Then `StudioDoubler` timing, pitch, level and tone per pick, with each take's own source.
- `StudioDoubler` keeps every finished take in `take_signals` (for take-per-track output and the tests).
- Results (each take through its own amp): quad comb, bend / play again / true quad: chug 0.069 / 0.068 / 0.057,
  chords 0.058 / 0.061 / 0.058, lead 0.073 / 0.108 / 0.064. **With one amp per take, even bent copies come close.**
- The lead's 0.108 is a fault of the measure, not a flanger: the peak sits at the notes' own period (3–5 ms),
  because the new residual fills the gaps between overtones differently from the input. The synthetic true takes
  have no noise between overtones. New overtone phases with the old residual: 0.064; old phases with new residual:
  0.060. A better flanger measure is needed for this engine (open).
- Listening files: bend / play again / true, double and quad, each take through its own amp.
- Open: per-pick pitch in this engine still comes from the varispeed; the analysis could play each pick at its own
  pitch instead. Real DI recordings not tested yet (the synthetic guitar has no string noise, so play-again and
  bend may sound closer than they will on a real guitar).

