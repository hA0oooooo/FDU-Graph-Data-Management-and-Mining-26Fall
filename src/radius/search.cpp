#include "graph.hpp"
#include <chrono>
#include <iostream>

int main(int argc, char** argv) {
    using namespace khop;
    using Clock = std::chrono::steady_clock;
    if (argc != 4) throw std::runtime_error("search N graph.edges test.tsv");
    const auto graph = Graph::load(std::stoul(argv[1]), argv[2]);
    std::ifstream file(argv[3]);
    std::string header;
    std::getline(file, header);
    std::vector<Query> queries;
    Query query;
    while (file >> query.s >> query.t >> query.k >> query.d) queries.push_back(query);
    if (header != "s\tt\tk\td" || queries.empty() || !file.eof())
        throw std::runtime_error("invalid query file");
    std::vector<char> answers(queries.size());
    std::cout << "method\tqueries\tmismatches\tscans\tbatch_ms\n";
    for (bool bidirectional : {false, true}) {
        Search search(graph);
        Count scans = 0;
        const auto begin = Clock::now();
        for (size_t i = 0; i < queries.size(); ++i) {
            const auto result = search.run(queries[i], bidirectional);
            answers[i] = result.yes;
            scans += result.scans;
        }
        const auto ms = std::chrono::duration<double, std::milli>(Clock::now() - begin).count();
        size_t errors = 0;
        for (size_t i = 0; i < queries.size(); ++i) {
            const auto& q = queries[i];
            errors += bool(answers[i]) != (q.d >= 0 && q.d <= q.k);
        }
        std::cout << (bidirectional ? "bibfs" : "bfs") << '\t' << queries.size() << '\t'
                  << errors << '\t' << scans << '\t' << ms << '\n';
    }
}
