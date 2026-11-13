#pragma once

// Small helpers shared by the tests: test signals, block-wise processing, measurements.

#include "tp/Engine.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

namespace tp::test
{

constexpr double pi = 3.14159265358979323846;

using Signal = std::vector<float>;

inline Signal sine(double freq, double sampleRate, int length, float amplitude = 0.5f)
{
    Signal x(static_cast<size_t>(length));
    for (int n = 0; n < length; ++n)
        x[static_cast<size_t>(n)] = amplitude * static_cast<float>(std::sin(2.0 * pi * freq * n / sampleRate));
    return x;
}

// Deterministic white noise in -amplitude ... +amplitude.
inline Signal noise(int length, float amplitude = 0.5f, uint32_t seed = 12345)
{
    Signal x(static_cast<size_t>(length));
    for (auto& v : x)
    {
        seed = seed * 1664525u + 1013904223u;
        v = amplitude * (static_cast<float>(seed >> 8) / 8388608.0f - 1.0f);
    }
    return x;
}

// Runs a mono signal through an engine in blocks, like a host does.
inline Signal processMono(Engine& engine, const Signal& in, int blockSize)
{
    Signal out(in.size());
    for (size_t start = 0; start < in.size(); start += static_cast<size_t>(blockSize))
    {
        const int n = static_cast<int>(std::min<size_t>(static_cast<size_t>(blockSize), in.size() - start));
        const float* inPtr = in.data() + start;
        float* outPtr = out.data() + start;
        engine.process(&inPtr, &outPtr, n);
    }
    return out;
}

inline double rms(const Signal& x, size_t from, size_t to)
{
    double sum = 0.0;
    for (size_t i = from; i < to; ++i)
        sum += static_cast<double>(x[i]) * x[i];
    return std::sqrt(sum / static_cast<double>(to - from));
}

inline double toDb(double gain)
{
    return 20.0 * std::log10(std::max(gain, 1e-12));
}

// Lag (in samples) within [minLag, maxLag] where `out` best matches `in`,
// using normalised cross-correlation over in[from ... from + length).
struct Match
{
    int lag = 0;
    double correlation = 0.0;
};

inline Match bestLag(const Signal& in, const Signal& out, int minLag, int maxLag, size_t from, size_t length)
{
    Match best;
    for (int lag = minLag; lag <= maxLag; ++lag)
    {
        double xy = 0.0, xx = 0.0, yy = 0.0;
        for (size_t i = from; i < from + length; ++i)
        {
            const double x = in[i];
            const double y = out[i + static_cast<size_t>(lag)];
            xy += x * y;
            xx += x * x;
            yy += y * y;
        }
        const double c = xy / std::sqrt(xx * yy + 1e-30);
        if (c > best.correlation)
            best = { lag, c };
    }
    return best;
}

inline bool allFinite(const Signal& x)
{
    return std::all_of(x.begin(), x.end(), [](float v) { return std::isfinite(v); });
}

} // namespace tp::test
