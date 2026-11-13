# tp_core: the DSP. Plain C++20, no JUCE, so it can be tested and reused on its own.
add_library(tp_core STATIC
    src/DelayLine.cpp
    src/PassThroughEngine.cpp
    src/SignalsmithEngine.cpp)

target_include_directories(tp_core PUBLIC include)
target_compile_features(tp_core PUBLIC cxx_std_20)
target_link_libraries(tp_core PRIVATE signalsmith-stretch)

if(MSVC)
    # /bigobj: Signalsmith Linear has more templates than the default object format allows
    target_compile_options(tp_core PRIVATE /W4 /permissive- /bigobj)
else()
    target_compile_options(tp_core PRIVATE -Wall -Wextra)
endif()
