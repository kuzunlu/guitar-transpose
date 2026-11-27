# Dependencies

Every dependency is pinned to an exact version. Never use a branch name or "latest".

## Built into the plugin

| Name | Version | Pinned by | License | Notes |
|------|---------|-----------|---------|-------|
| JUCE | 9.0.5 (tag commit `d60b7a78030661574a615b586d9325ba7a7fa7dd`, released 2026-11-02) | `CMakeLists.txt`: zip URL + SHA-256 `db891ee990a5ec8b58739f24e1ac62d8abd584205256a356c414a083d8927168` | AGPLv3 **or** the commercial JUCE 9 licence | Used under the free **Starter** tier (up to $20,000 revenue in the last 12 months; above that, Indie). No splash screen needed. JUCE files must not be put in this repo (CMake downloads them). EULA: https://juce.com/legal/juce-9-licence/ |
| VST3 SDK | 3.8.0 (bundled inside JUCE 9.0.5) | comes with JUCE | MIT | |
| Signalsmith Stretch | 1.4.0 (tag commit `a670068d9aeb64913331d5cc29337b19a457a7df`, released 2026-09-25) | `CMakeLists.txt`: zip URL + SHA-256 `758960fbafaa0550d17626b1eb9497d0fd10f80dad00e96590099ef6c20390e6` | MIT | Studio engine, and the temporary Live engine until M3. Header-only. |
| Signalsmith Linear | 0.6.4 (tag commit `de55e6a50ffcf6f8f43f649692d94691c7025151`, released 2026-09-25) | `CMakeLists.txt`: zip URL + SHA-256 `eff8c9f8f2573d1f8ef52a93de32c68a70547e5c07cc1ccf62fb41795d651056` | MIT | Needed by Stretch. Declared before Stretch so Stretch does not fetch its own copy by tag name. Needs `/bigobj` with MSVC. |

## Test only (linked into `tp_tests`, never into the plugin)

| Name | Version | Pinned by | License |
|------|---------|-----------|---------|
| Catch2 | 3.16.1 (released 2026-10-08) | `CMakeLists.txt`: zip URL + SHA-256 `7509086e230246c393e82a4065b0c2b3b934c3f9e0572b7ab4927a74cf50efc0` | BSL-1.0 |

## Tools only (never linked into the plugin)

| Name | Version | Where | License | Notes |
|------|---------|-------|---------|-------|
| pluginval (Tracktion) | 1.0.4 (released 2024-12-04) | `tools/bin/pluginval-1.0.4/` (git-ignored). Download: https://github.com/Tracktion/pluginval/releases/download/v1.0.4/pluginval_Windows.zip, zip SHA-256 `c08e61ce3b96db41636f8ec7e76f4c7e2c13ebdac7fa1b5a1f52b4f32ec715ab` | GPLv3 | Not code-signed. Run with `scripts\pluginval.bat`. |
| Visual Studio Build Tools 2026 | 18.8, MSVC 14.51.36231, Windows SDK 10.0.26100.0 | installed on the machine | Microsoft | |
| CMake | 4.3.1 (inside Build Tools) | installed on the machine | BSD-3 | Project needs 3.25 or newer. |
| Ninja | inside Build Tools | installed on the machine | Apache-2.0 | |
| Python | 3.14.7 + NumPy 2.5.3 | installed on the machine | PSF / BSD | For `reference/` only. |

## Planned, not added yet

| Name | For | License |
|------|-----|---------|
| PFFFT (marton78 fork), or the FFT in Signalsmith Linear (already here) | FFT in the predictive engine (M4) | BSD-like / MIT |
| Steinberg VST3 validator | stricter VST3 check (M7); pluginval skips this test without it | MIT (VST3 SDK) |

## Network note

On this machine, Git Bash's `curl` fails on GitHub with `CRYPT_E_NO_REVOCATION_CHECK` (it cannot reach the certificate revocation server). PowerShell's `Invoke-WebRequest` and CMake's own download work. Use those.
