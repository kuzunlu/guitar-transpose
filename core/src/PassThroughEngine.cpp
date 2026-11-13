#include "tp/PassThroughEngine.h"

#include <algorithm>

namespace tp
{

void PassThroughEngine::prepare(double, int, int numChannels)
{
    channels = numChannels;
}

void PassThroughEngine::process(const float* const* in, float* const* out, int numSamples)
{
    for (int ch = 0; ch < channels; ++ch)
        if (in[ch] != out[ch])
            std::copy(in[ch], in[ch] + numSamples, out[ch]);
}

} // namespace tp
