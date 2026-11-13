#include "tp/SignalsmithEngine.h"

// The library headers are not /W4 clean. Silence them only, not our own code.
#if defined(_MSC_VER)
    #pragma warning(push, 0)
#endif
#include <signalsmith-stretch/signalsmith-stretch.h>
#if defined(_MSC_VER)
    #pragma warning(pop)
#endif

#include <algorithm>
#include <vector>

namespace tp
{

struct SignalsmithEngine::Impl
{
    Preset preset;
    signalsmith::stretch::SignalsmithStretch<float> stretch { 0x5eed }; // fixed seed: same output every run
    // The library divides by its block size, so it must not be touched before configure().
    // Hosts may call reset() (via releaseResources) before the first prepare.
    bool configured = false;
    int channels = 0;
    int maxBlock = 0;
    double ratio = 1.0;
    double appliedRatio = 0.0;

    // The library reads input while it writes output, so it cannot work in place.
    std::vector<std::vector<float>> scratch;
    std::vector<float*> scratchPtrs;
    std::vector<const float*> inPtrs;
};

SignalsmithEngine::SignalsmithEngine(Preset preset) : impl(std::make_unique<Impl>())
{
    impl->preset = preset;
}

SignalsmithEngine::~SignalsmithEngine() = default;

void SignalsmithEngine::prepare(double sampleRate, int maxBlockSize, int numChannels)
{
    auto& s = *impl;
    s.channels = numChannels;
    s.maxBlock = std::max(maxBlockSize, 1);
    s.configured = numChannels > 0 && sampleRate > 0.0;

    if (! s.configured)
        return;

    if (s.preset == Preset::Studio)
        s.stretch.presetDefault(numChannels, static_cast<float>(sampleRate));
    else
        s.stretch.configure(numChannels, static_cast<int>(sampleRate * 0.04), static_cast<int>(sampleRate * 0.01));

    s.scratch.assign(static_cast<size_t>(numChannels), std::vector<float>(static_cast<size_t>(s.maxBlock), 0.0f));
    s.scratchPtrs.resize(static_cast<size_t>(numChannels));
    s.inPtrs.resize(static_cast<size_t>(numChannels));
    for (size_t ch = 0; ch < s.scratch.size(); ++ch)
        s.scratchPtrs[ch] = s.scratch[ch].data();

    s.appliedRatio = 0.0; // force setTransposeFactor on the next block
    reset();
}

void SignalsmithEngine::setRatio(double ratio)
{
    impl->ratio = ratio;
}

int SignalsmithEngine::latencySamples() const
{
    if (! impl->configured)
        return 0;
    return impl->stretch.inputLatency() + impl->stretch.outputLatency();
}

void SignalsmithEngine::process(const float* const* in, float* const* out, int numSamples)
{
    auto& s = *impl;

    if (! s.configured)
        return;

    if (s.ratio != s.appliedRatio)
    {
        s.stretch.setTransposeFactor(static_cast<float>(s.ratio));
        s.appliedRatio = s.ratio;
    }

    // Hosts may send more than maxBlockSize; work in pieces that fit the scratch buffers.
    for (int start = 0; start < numSamples; start += s.maxBlock)
    {
        const int n = std::min(s.maxBlock, numSamples - start);

        for (size_t ch = 0; ch < s.inPtrs.size(); ++ch)
            s.inPtrs[ch] = in[ch] + start;

        s.stretch.process(s.inPtrs.data(), n, s.scratchPtrs.data(), n);

        for (size_t ch = 0; ch < s.scratch.size(); ++ch)
            std::copy(s.scratch[ch].begin(), s.scratch[ch].begin() + n, out[ch] + start);
    }
}

void SignalsmithEngine::reset()
{
    if (impl->configured)
        impl->stretch.reset();
}

} // namespace tp
