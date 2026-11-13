#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

#include "tp/DelayLine.h"
#include "tp/SignalsmithEngine.h"

class TransposeProcessor final : public juce::AudioProcessor
{
public:
    TransposeProcessor();

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;

    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    using AudioProcessor::processBlock;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 0.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

private:
    enum Mode { live = 0, studio = 1 };

    static juce::AudioProcessorValueTreeState::ParameterLayout createParameters();
    tp::Engine& engineFor (int mode);
    void updateLatency();

    juce::AudioProcessorValueTreeState params;
    std::atomic<float>* transposeParam = nullptr;
    std::atomic<float>* fineParam = nullptr;
    std::atomic<float>* modeParam = nullptr;
    std::atomic<float>* mixParam = nullptr;
    std::atomic<float>* outputParam = nullptr;

    tp::SignalsmithEngine liveEngine { tp::SignalsmithEngine::Preset::LowLatency };
    tp::SignalsmithEngine studioEngine { tp::SignalsmithEngine::Preset::Studio };
    int currentMode = live;

    tp::DelayLine dryDelay;
    juce::AudioBuffer<float> dryBuffer;

    // 1 = output the engine, 0 = output the delayed dry signal
    juce::SmoothedValue<float> wetAmount;
    juce::SmoothedValue<float, juce::ValueSmoothingTypes::Multiplicative> outputGain;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (TransposeProcessor)
};
