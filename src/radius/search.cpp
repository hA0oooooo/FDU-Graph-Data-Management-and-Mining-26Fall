#include "graph.hpp"
#include "../benchmark_metrics.hpp"
#include <chrono>
#include <iostream>
#include <filesystem>

int main(int argc, char** argv) {
    using namespace khop;
    using Clock = std::chrono::steady_clock;
    if (argc < 4 || argc > 6) throw std::runtime_error("search N graph.edges test.tsv [answer-dir [bfs|bibfs]]");
    const auto graph = Graph::load(std::stoul(argv[1]), argv[2]);
    std::ifstream file(argv[3]);
    std::string header;
    std::getline(file, header);
    std::vector<Query> queries;
    Query query;
    while (file >> query.s >> query.t >> query.k >> query.d) queries.push_back(query);
    if (header != "s\tt\tk\td" || queries.empty() || !file.eof())
        throw std::runtime_error("invalid query file");
    std::cout << "method\tqueries\tmismatches\tscans\tbatch_ms\tmedian_batch_ms\tquery_repeats\tready_rss_kib\n";
    for (bool bidirectional : {false, true}) {
        std::string method=bidirectional?"bibfs":"bfs";
        if(argc==6 && method!=argv[5])continue;
        Search search(graph);
        Count scans = 0;
        uint64_t ready=khop_bench::rss_kib();
        auto timing=khop_bench::measure(queries.size(),[&](size_t i){
            auto result=search.run(queries[i],bidirectional);
            scans+=result.scans;
            return result.yes;
        });
        const auto& answers=timing.answers;
        scans/=timing.repeats+1;
        size_t errors = 0;
        for (size_t i = 0; i < queries.size(); ++i) {
            const auto& q = queries[i];
            errors += bool(answers[i]) != (q.d >= 0 && q.d <= q.k);
        }
        if (argc >= 5) {
            const std::filesystem::path folder=argv[4];
            std::filesystem::create_directories(folder);
            std::ofstream output(folder/(std::string(bidirectional?"bibfs":"bfs")+".tsv"));
            output<<"answer\n";
            for(char value:answers) output<<int(value)<<'\n';
        }
        std::cout << (bidirectional ? "bibfs" : "bfs") << '\t' << queries.size() << '\t'
                  << errors << '\t' << scans << '\t' << timing.first_ns/1e6 << '\t' << timing.median_ns/1e6
                  << '\t' << timing.repeats << '\t' << ready << '\n';
    }
}
