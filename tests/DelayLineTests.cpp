#include "tp/DelayLine.h"

#include <catch2/catch_test_macros.hpp>

#include <vector>

TEST_CASE("DelayLine delays by exactly the set amount, across block borders")
{
    tp::DelayLine d;
    d.prepare(1, 100);
    d.setDelay(37);

    std::vector<float> in(200, 0.0f), out(200, 1.0f);
    in[10] = 1.0f;

    for (int start = 0; start < 200; start += 16)
    {
        const int n = std::min(16, 200 - start);
        const float* i = in.data() + start;
        float* o = out.data() + start;
        d.process(&i, &o, n);
    }

    for (int k = 0; k < 200; ++k)
        CHECK(out[static_cast<size_t>(k)] == (k == 47 ? 1.0f : 0.0f));
}

TEST_CASE("DelayLine works in place and with zero delay")
{
    tp::DelayLine d;
    d.prepare(2, 8);

    std::vector<float> a { 1, 2, 3, 4, 5, 6 }, b { 6, 5, 4, 3, 2, 1 };
    float* ptrs[] = { a.data(), b.data() };

    d.setDelay(0);
    d.process(ptrs, ptrs, 6);
    CHECK(a == std::vector<float> { 1, 2, 3, 4, 5, 6 });
    CHECK(b == std::vector<float> { 6, 5, 4, 3, 2, 1 });

    d.reset();
    d.setDelay(2);
    d.process(ptrs, ptrs, 6);
    CHECK(a == std::vector<float> { 0, 0, 1, 2, 3, 4 });
    CHECK(b == std::vector<float> { 0, 0, 6, 5, 4, 3 });
}

TEST_CASE("DelayLine clamps the delay to its size")
{
    tp::DelayLine d;
    d.prepare(1, 10);
    d.setDelay(50);
    CHECK(d.getDelay() == 10);
    d.setDelay(-3);
    CHECK(d.getDelay() == 0);
}
