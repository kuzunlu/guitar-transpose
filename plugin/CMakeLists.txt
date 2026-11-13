# The VST3 wrapper. Only plugin glue lives here; the DSP is in tp_core.
#
# COMPANY_NAME, PRODUCT_NAME and the two 4-letter codes are placeholders.
# Choose the final ones before the plugin is used in real Ableton projects:
# the VST3 ID is made from the codes, and changing them later means old
# projects can no longer find the plugin.
juce_add_plugin(TransposePlugin
    COMPANY_NAME "KU Audio"
    PRODUCT_NAME "Guitar Transpose"
    BUNDLE_ID com.kuaudio.guitartranspose
    PLUGIN_MANUFACTURER_CODE Kuzu
    PLUGIN_CODE Gtrp
    FORMATS VST3 Standalone
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD FALSE
    VST3_CATEGORIES Fx "Pitch Shift")

target_sources(TransposePlugin PRIVATE
    PluginProcessor.cpp)

target_compile_definitions(TransposePlugin PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0)

target_link_libraries(TransposePlugin
    PRIVATE
        tp_core
        juce::juce_audio_utils
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags)
