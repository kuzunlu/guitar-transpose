#pragma once

#include "tp/Engine.h"

#include <memory>

namespace tp
{

// Wraps Signalsmith Stretch (MIT) as a pitch shifter with no time change.
//   Studio:     the library's default preset (120 ms blocks). High quality, high latency.
//   LowLatency: 40 ms blocks. A stand-in for Live mode until our own engine is
//               ported (PLAN.md milestone M3). Remove it then.
class SignalsmithEngine final : public Engine
{
public:
    enum class Preset { Studio, LowLatency };

    explicit SignalsmithEngine(Preset preset);
    ~SignalsmithEngine() override;

    void prepare(double sampleRate, int maxBlockSize, int numChannels) override;
    void setRatio(double ratio) override;
    int latencySamples() const override;
    void process(const float* const* in, float* const* out, int numSamples) override;
    void reset() override;

private:
    struct Impl;
    std::unique_ptr<Impl> impl;
};

} // namespace tp
