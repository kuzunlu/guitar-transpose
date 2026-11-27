# Guitar Transpose

A VST3 plugin for guitar, made for Ableton Live on Windows. **Work in progress, not ready to use.**

It will have two parts:

- **Transpose**: shifts a guitar DI up or down in pitch with very low delay, so you can play in a lower tuning without retuning. Made for 6- and 7-string guitar.
- **Doubler**: turns one take into a real-sounding double or quad track. Each new take gets its own small timing, pitch and tone changes, like a human playing the part again. It is not a simple widener or a delayed copy.

The plugin will be renamed to **Guitar Tools** before the first release (v0.1.0).

## Where the project stands

- The sound engines are first built and tested in Python + NumPy, in `reference/`. These files are the spec for the C++ code.
- The plugin shell is in C++ with JUCE. Right now it uses the Signalsmith Stretch library as a temporary engine.
- The doubler is still in the Python research stage.

The full plan is in [PLAN.md](PLAN.md). Decisions are in [docs/DECISIONS.md](docs/DECISIONS.md), measured numbers in [docs/RESULTS.md](docs/RESULTS.md).

## Build (Windows)

Needs Visual Studio Build Tools 2026 with the C++ workload (it includes CMake and Ninja).
JUCE, Signalsmith and Catch2 are downloaded by CMake at pinned versions (see [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)).

```
scripts\build.bat Release
scripts\test.bat Release
```

The plugin ends up in `build\Release\plugin\TransposePlugin_artefacts\Release\VST3\`.

## Python reference

Needs Python 3.14 and NumPy.

```
cd reference
python run_tests.py all
python render.py in.wav out.wav -2
```

## License

All rights reserved. You may read the code, but not copy or reuse it.
JUCE is used under its free Starter licence.
