cmake_minimum_required(VERSION 3.25)

project(TransposePlugin VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)

# JUCE 9.0.5, tag commit d60b7a78030661574a615b586d9325ba7a7fa7dd.
# The hash pins the exact zip. See docs/DEPENDENCIES.md before changing it.
FetchContent_Declare(JUCE
    URL https://github.com/juce-framework/JUCE/archive/refs/tags/9.0.5.zip
    URL_HASH SHA256=db891ee990a5ec8b58739f24e1ac62d8abd584205256a356c414a083d8927168
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(JUCE)

# Signalsmith Linear 0.6.4 (tag commit de55e6a50ffcf6f8f43f649692d94691c7025151).
# Declared here, before Stretch, so Stretch uses this pinned copy instead of its own tag-only fetch.
FetchContent_Declare(signalsmith-linear
    URL https://github.com/Signalsmith-Audio/linear/archive/refs/tags/0.6.4.zip
    URL_HASH SHA256=eff8c9f8f2573d1f8ef52a93de32c68a70547e5c07cc1ccf62fb41795d651056
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)

# Signalsmith Stretch 1.4.0 (tag commit a670068d9aeb64913331d5cc29337b19a457a7df).
FetchContent_Declare(signalsmith-stretch
    URL https://github.com/Signalsmith-Audio/signalsmith-stretch/archive/refs/tags/1.4.0.zip
    URL_HASH SHA256=758960fbafaa0550d17626b1eb9497d0fd10f80dad00e96590099ef6c20390e6
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(signalsmith-linear signalsmith-stretch)

add_subdirectory(core)
add_subdirectory(plugin)

option(TP_BUILD_TESTS "Build the tp_core unit tests" ON)
if(TP_BUILD_TESTS)
    # Catch2 v3.16.1 (released 2026-10-08)
    FetchContent_Declare(Catch2
        URL https://github.com/catchorg/Catch2/archive/refs/tags/v3.16.1.zip
        URL_HASH SHA256=7509086e230246c393e82a4065b0c2b3b934c3f9e0572b7ab4927a74cf50efc0
        DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
    FetchContent_MakeAvailable(Catch2)

    enable_testing()
    add_subdirectory(tests)
endif()
