#pragma once

namespace tp
{

// Every engine implements this, so the plugin can swap engines with one setting.
// See PLAN.md section 11 for the real-time rules that apply to process().
struct Engine
{
    virtual ~Engine() = default;

    virtual void prepare(double sampleRate, int maxBlockSize, int numChannels) = 0;
    virtual void setRatio(double ratio) = 0;      // smoothed inside the engine
    virtual int latencySamples() const = 0;       // for the current ratio sign
    virtual void process(const float* const* in, float* const* out, int numSamples) = 0;
    virtual void reset() = 0;
};

} // namespace tp
