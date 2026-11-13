#pragma once

#include <vector>

namespace tp
{

// Whole-sample delay for several channels. Used to line up the dry signal with
// an engine's output. Input and output may be the same buffers.
class DelayLine
{
public:
    // Allocates. Call outside the audio thread.
    void prepare(int numChannels, int maxDelaySamples);

    // Clamped to 0 ... maxDelaySamples.
    void setDelay(int samples);
    int getDelay() const { return delay; }

    void process(const float* const* in, float* const* out, int numSamples);
    void reset();

private:
    std::vector<std::vector<float>> buffers;
    int size = 1;
    int writePos = 0;
    int delay = 0;
};

} // namespace tp
