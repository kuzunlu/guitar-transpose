#pragma once

#include "tp/Engine.h"

namespace tp
{

// Copies input to output. Used to prove the plugin chain (milestone M0).
class PassThroughEngine final : public Engine
{
public:
    void prepare(double sampleRate, int maxBlockSize, int numChannels) override;
    void setRatio(double) override {}
    int latencySamples() const override { return 0; }
    void process(const float* const* in, float* const* out, int numSamples) override;
    void reset() override {}

private:
    int channels = 0;
};

} // namespace tp
