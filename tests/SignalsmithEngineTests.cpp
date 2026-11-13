#include "TestSignals.h"

#include "tp/SignalsmithEngine.h"

#include <catch2/catch_test_macros.hpp>
#include <catch2/generators/catch_generators.hpp>

#include <cmath>
#include <cstdio>

using namespace tp::test;
using Preset = tp::SignalsmithEngine::Preset;

namespace
{
constexpr double fs = 48000.0;

const char* name(Preset p)
{
    return p == Preset::Studio ? "Studio" : "LowLatency";
}
} // namespace

TEST_CASE("Signalsmith: reported latency equals measured latency")
{
    const auto preset = GENERATE(Preset::Studio, Preset::LowLatency);

    tp::SignalsmithEngine engine(preset);
    engine.prepare(fs, 64, 1);
    engine.setRatio(1.0);
    const int reported = engine.latencySamples();

    const auto in = noise(static_cast<int>(fs * 2));
    const auto out = processMono(engine, in, 64);

    const auto match = bestLag(in, out, std::max(0, reported - 2000), reported + 2000, 4800, 24000);
    std::printf("  %-10s reported %5d, measured %5d samples (correlation %.3f)\n",
                name(preset), reported, match.lag, match.correlation);

    CHECK(match.lag == reported);
    CHECK(match.correlation > 0.9);
}

TEST_CASE("Signalsmith: output level against input level at each shift")
{
    // PLAN M1: correct with a fixed gain per shift if any is off by more than 0.5 dB.
    const auto preset = GENERATE(Preset::Studio, Preset::LowLatency);
    const auto freq = GENERATE(110.0, 440.0, 1500.0);

    for (int semitones : { -12, -7, -5, -2, -1, 2, 5, 12 })
    {
        tp::SignalsmithEngine engine(preset);
        engine.prepare(fs, 64, 1);
        engine.setRatio(std::pow(2.0, semitones / 12.0));

        const auto in = sine(freq, fs, static_cast<int>(fs * 2));
        const auto out = processMono(engine, in, 64);

        const double levelDb = toDb(rms(out, 48000, 96000) / rms(in, 48000, 96000));
        std::printf("  %-10s %6.0f Hz %+3d st: level %+5.2f dB\n", name(preset), freq, semitones, levelDb);

        CHECK(std::abs(levelDb) < 0.5);
    }
}

TEST_CASE("Signalsmith: same output for different host block sizes")
{
    const auto in = noise(static_cast<int>(fs));

    tp::SignalsmithEngine a(Preset::Studio), b(Preset::Studio);
    a.prepare(fs, 1024, 1);
    b.prepare(fs, 1024, 1);
    a.setRatio(std::pow(2.0, -2.0 / 12.0));
    b.setRatio(std::pow(2.0, -2.0 / 12.0));

    const auto outA = processMono(a, in, 64);
    const auto outB = processMono(b, in, 1000);

    double maxDiff = 0.0;
    for (size_t i = 0; i < in.size(); ++i)
        maxDiff = std::max(maxDiff, static_cast<double>(std::abs(outA[i] - outB[i])));

    std::printf("  block 64 vs 1000: largest difference %.2f dB below full scale\n", -toDb(maxDiff));
    CHECK(maxDiff < 1e-5);
}

TEST_CASE("Signalsmith: blocks longer than maxBlockSize are handled")
{
    tp::SignalsmithEngine engine(Preset::Studio);
    engine.prepare(fs, 64, 1);
    engine.setRatio(0.9);

    const auto out = processMono(engine, noise(9600), 3000);
    CHECK(allFinite(out));
}

TEST_CASE("Signalsmith: runs at every common sample rate, mono and stereo")
{
    const auto preset = GENERATE(Preset::Studio, Preset::LowLatency);
    const auto rate = GENERATE(22050.0, 44100.0, 48000.0, 88200.0, 96000.0, 192000.0);
    const auto channels = GENERATE(1, 2);

    tp::SignalsmithEngine engine(preset);
    engine.prepare(rate, 512, channels);
    engine.setRatio(0.89);

    const auto in = noise(static_cast<int>(rate / 2));
    Signal outL(in.size()), outR(in.size());
    const float* ins[] = { in.data(), in.data() };
    float* outs[] = { outL.data(), outR.data() };
    engine.process(ins, outs, static_cast<int>(in.size()));

    CAPTURE(name(preset), rate, channels);
    CHECK(allFinite(outL));
    CHECK(engine.latencySamples() > 0);
}

TEST_CASE("Signalsmith: odd host calls do not crash")
{
    const auto preset = GENERATE(Preset::Studio, Preset::LowLatency);
    CAPTURE(name(preset));

    SECTION("calls before prepare")
    {
        tp::SignalsmithEngine engine(preset);
        engine.reset();
        CHECK(engine.latencySamples() >= 0);
        engine.setRatio(0.9);
        engine.process(nullptr, nullptr, 0);
    }
    SECTION("zero-length blocks")
    {
        tp::SignalsmithEngine engine(preset);
        engine.prepare(fs, 512, 2);
        engine.setRatio(0.9);
        float l = 0, r = 0;
        const float* ins[] = { &l, &r };
        float* outs[] = { &l, &r };
        engine.process(ins, outs, 0);
        CHECK(std::isfinite(l));
    }
    SECTION("zero channels")
    {
        tp::SignalsmithEngine engine(preset);
        engine.prepare(fs, 512, 0);
        engine.setRatio(0.9);
        engine.process(nullptr, nullptr, 256);
        CHECK(engine.latencySamples() >= 0);
    }
}

TEST_CASE("Signalsmith: no NaN or Inf on difficult signals")
{
    Signal silence(48000, 0.0f), dc(48000, 0.9f), square(48000), loud = noise(48000, 1.0f);
    for (size_t i = 0; i < square.size(); ++i)
        square[i] = (i / 50) % 2 ? 1.0f : -1.0f;

    for (const auto* sig : { &silence, &dc, &square, &loud })
        for (double ratio : { 0.5, 0.89, 1.12, 2.0 })
        {
            tp::SignalsmithEngine engine(Preset::LowLatency);
            engine.prepare(fs, 128, 1);
            engine.setRatio(ratio);
            CHECK(allFinite(processMono(engine, *sig, 128)));
        }
}
