#include "tp/DelayLine.h"

#include <algorithm>

namespace tp
{

void DelayLine::prepare(int numChannels, int maxDelaySamples)
{
    size = std::max(maxDelaySamples, 0) + 1;
    buffers.assign(static_cast<size_t>(numChannels), std::vector<float>(static_cast<size_t>(size), 0.0f));
    writePos = 0;
    delay = std::min(delay, size - 1);
}

void DelayLine::setDelay(int samples)
{
    delay = std::clamp(samples, 0, size - 1);
}

void DelayLine::process(const float* const* in, float* const* out, int numSamples)
{
    int pos = writePos;

    for (size_t ch = 0; ch < buffers.size(); ++ch)
    {
        auto& buf = buffers[ch];
        pos = writePos;

        for (int i = 0; i < numSamples; ++i)
        {
            buf[static_cast<size_t>(pos)] = in[ch][i];
            int readPos = pos - delay;
            if (readPos < 0)
                readPos += size;
            out[ch][i] = buf[static_cast<size_t>(readPos)];
            if (++pos == size)
                pos = 0;
        }
    }

    writePos = pos;
}

void DelayLine::reset()
{
    for (auto& buf : buffers)
        std::fill(buf.begin(), buf.end(), 0.0f);
    writePos = 0;
}

} // namespace tp
