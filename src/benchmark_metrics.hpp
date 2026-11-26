#pragma once
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <unistd.h>
#include <vector>

namespace khop_bench {
inline unsigned repetitions() {
    const char* value=std::getenv("KHOP_QUERY_REPEATS");
    int n=value?std::stoi(value):5;
    if(n<1)throw std::invalid_argument("KHOP_QUERY_REPEATS must be positive");
    return unsigned(n);
}

inline uint64_t rss_kib() {
    std::ifstream stat("/proc/self/statm");
    uint64_t total=0,resident=0;
    if(!(stat>>total>>resident))throw std::runtime_error("cannot read process RSS");
    return resident*uint64_t(sysconf(_SC_PAGESIZE))/1024;
}

struct BatchTiming {
    std::vector<uint8_t> answers;
    uint64_t first_ns,median_ns;
    unsigned repeats;
};

// Exactly one warm-up batch followed by R measured identical batches.
// Prediction consistency is checked outside the timed region.
template<class Query>
BatchTiming measure(size_t n, Query query) {
    using Clock=std::chrono::steady_clock;
    std::vector<uint8_t> answers(n),warm(n);
    for(size_t i=0;i<n;++i)warm[i]=query(i);
    unsigned repeat=repetitions();
    std::vector<uint64_t> timings;
    timings.reserve(repeat);
    for(unsigned i=0;i<repeat;++i) {
        auto began=Clock::now();
        for(size_t j=0;j<n;++j)answers[j]=query(j);
        timings.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-began).count());
        if(answers!=warm)throw std::logic_error("query result changed between batches");
    }
    uint64_t first=timings.front();
    std::sort(timings.begin(),timings.end());
    uint64_t median=(timings[(repeat-1)/2]+timings[repeat/2])/2;
    return BatchTiming{std::move(answers),first,median,repeat};
}
}
