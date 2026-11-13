#include "PluginProcessor.h"

#include <cmath>

namespace
{
constexpr double smoothingSeconds = 0.02;
}

TransposeProcessor::TransposeProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput ("Input", juce::AudioChannelSet::stereo(), true)
                          .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      params (*this, nullptr, "TransposeState", createParameters())
{
    transposeParam = params.getRawParameterValue ("transpose");
    fineParam = params.getRawParameterValue ("fine");
    modeParam = params.getRawParameterValue ("mode");
    mixParam = params.getRawParameterValue ("mix");
    outputParam = params.getRawParameterValue ("output");
}

juce::AudioProcessorValueTreeState::ParameterLayout TransposeProcessor::createParameters()
{
    using namespace juce;

    // IDs are saved in Ableton projects. Never rename them; add new ones instead.
    return {
        std::make_unique<AudioParameterInt> (ParameterID { "transpose", 1 }, "Transpose", -12, 12, 0,
                                             AudioParameterIntAttributes().withLabel ("st")),
        std::make_unique<AudioParameterInt> (ParameterID { "fine", 1 }, "Fine", -50, 50, 0,
                                             AudioParameterIntAttributes().withLabel ("cents")),
        std::make_unique<AudioParameterChoice> (ParameterID { "mode", 1 }, "Mode", StringArray { "Live", "Studio" }, live),
        std::make_unique<AudioParameterFloat> (ParameterID { "mix", 1 }, "Mix", NormalisableRange<float> (0.0f, 100.0f, 0.1f), 100.0f,
                                               AudioParameterFloatAttributes().withLabel ("%")),
        std::make_unique<AudioParameterFloat> (ParameterID { "output", 1 }, "Output", NormalisableRange<float> (-24.0f, 12.0f, 0.1f), 0.0f,
                                               AudioParameterFloatAttributes().withLabel ("dB")),
    };
}

tp::Engine& TransposeProcessor::engineFor (int mode)
{
    return mode == studio ? static_cast<tp::Engine&> (studioEngine) : static_cast<tp::Engine&> (liveEngine);
}

void TransposeProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    const int channels = getTotalNumOutputChannels();

    liveEngine.prepare (sampleRate, samplesPerBlock, channels);
    studioEngine.prepare (sampleRate, samplesPerBlock, channels);

    // room for the slowest engine
    dryDelay.prepare (channels, std::max (liveEngine.latencySamples(), studioEngine.latencySamples()));
    dryBuffer.setSize (channels, samplesPerBlock, false, false, true);

    wetAmount.reset (sampleRate, smoothingSeconds);
    outputGain.reset (sampleRate, smoothingSeconds);
    outputGain.setCurrentAndTargetValue (juce::Decibels::decibelsToGain (outputParam->load()));

    currentMode = static_cast<int> (modeParam->load());
    updateLatency();
}

void TransposeProcessor::releaseResources()
{
    liveEngine.reset();
    studioEngine.reset();
    dryDelay.reset();
}

void TransposeProcessor::updateLatency()
{
    const int latency = engineFor (currentMode).latencySamples();
    dryDelay.setDelay (latency);

    if (latency != getLatencySamples())
        setLatencySamples (latency);
}

bool TransposeProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    // mono in -> mono out, or stereo in -> stereo out
    const auto out = layouts.getMainOutputChannelSet();

    if (out != juce::AudioChannelSet::mono() && out != juce::AudioChannelSet::stereo())
        return false;

    return layouts.getMainInputChannelSet() == out;
}

void TransposeProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;

    const int numSamples = buffer.getNumSamples();
    const int channels = getTotalNumOutputChannels();

    for (auto ch = getTotalNumInputChannels(); ch < channels; ++ch)
        buffer.clear (ch, 0, numSamples);

    // A mode change swaps engines and changes the latency. It may click; it is not a playing control.
    const int mode = static_cast<int> (modeParam->load());
    if (mode != currentMode)
    {
        currentMode = mode;
        engineFor (currentMode).reset();
        updateLatency();
    }

    const int semitones = static_cast<int> (transposeParam->load());
    const int cents = static_cast<int> (fineParam->load());
    const double ratio = std::pow (2.0, (semitones + cents / 100.0) / 12.0);

    auto& engine = engineFor (currentMode);
    engine.setRatio (ratio);
    updateLatency(); // some engines need more delay for up-shifts

    // At 0 st / 0 cents the plugin outputs the dry signal, delayed by the same latency,
    // so switching to 0 does not move the track in time.
    const bool unshifted = semitones == 0 && cents == 0;
    wetAmount.setTargetValue (unshifted ? 0.0f : mixParam->load() / 100.0f);
    outputGain.setTargetValue (juce::Decibels::decibelsToGain (outputParam->load()));

    if (dryBuffer.getNumSamples() < numSamples)
        dryBuffer.setSize (channels, numSamples, false, false, true); // only if the host breaks its promise

    dryDelay.process (buffer.getArrayOfReadPointers(), dryBuffer.getArrayOfWritePointers(), numSamples);
    engine.process (buffer.getArrayOfReadPointers(), buffer.getArrayOfWritePointers(), numSamples);

    for (int i = 0; i < numSamples; ++i)
    {
        const float wet = wetAmount.getNextValue();
        const float gain = outputGain.getNextValue();

        for (int ch = 0; ch < channels; ++ch)
        {
            auto* out = buffer.getWritePointer (ch);
            const auto* dry = dryBuffer.getReadPointer (ch);
            out[i] = (wet * out[i] + (1.0f - wet) * dry[i]) * gain;
        }
    }
}

void TransposeProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    if (auto xml = params.copyState().createXml())
        copyXmlToBinary (*xml, destData);
}

void TransposeProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    if (auto xml = getXmlFromBinary (data, sizeInBytes))
        if (xml->hasTagName (params.state.getType()))
            params.replaceState (juce::ValueTree::fromXml (*xml));
}

juce::AudioProcessorEditor* TransposeProcessor::createEditor()
{
    return new juce::GenericAudioProcessorEditor (*this);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new TransposeProcessor();
}
