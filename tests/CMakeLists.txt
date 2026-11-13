add_executable(tp_tests
    DelayLineTests.cpp
    SignalsmithEngineTests.cpp)

target_link_libraries(tp_tests PRIVATE tp_core Catch2::Catch2WithMain)

if(MSVC)
    target_compile_options(tp_tests PRIVATE /W4 /permissive-)
endif()

add_test(NAME tp_tests COMMAND tp_tests)
