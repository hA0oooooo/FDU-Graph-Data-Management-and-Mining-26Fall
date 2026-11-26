#include "graph.hpp"
#include <cmath>
#include <iostream>
#include <random>
#include <set>

using namespace khop;

std::vector<int> full_distances(const Graph& graph, Node source) {
    const auto& adj = graph.side[1];
    std::vector<int> distance(graph.n, -1);
    std::vector<Node> queue{source};
    distance[source] = 0;
    for (size_t i = 0; i < queue.size(); ++i) {
        Node u = queue[i];
        for (auto j = adj.offsets[u]; j < adj.offsets[u+1]; ++j) {
            Node v = adj.neighbors[j];
            if (distance[v] >= 0) continue;
            distance[v] = distance[u] + 1;
            queue.push_back(v);
        }
    }
    return distance;
}

void emit(std::ostream& out, Node s, Node t, int k, int d) {
    out << s << '\t' << t << '\t' << k << '\t' << d << '\n';
}

int main(int argc, char** argv) {
    if (argc != 6) throw std::invalid_argument("benchmark_data N edges exclusions uniform.tsv stratified.tsv");
    const auto graph = Graph::load(std::stoul(argv[1]), argv[2]);
    std::ifstream exclude(argv[3]);
    std::set<Node> excluded;
    Node u;
    while (exclude >> u) excluded.insert(u);
    std::vector<Node> pool;
    for (Node v=0; v<graph.n; ++v) if (!excluded.count(v)) pool.push_back(v);
    std::mt19937 rng(26112026);
    std::shuffle(pool.begin(), pool.end(), rng);
    std::ofstream uniform(argv[4]), stratified(argv[5]);
    uniform << "s\tt\tk\td\n";
    stratified << "s\tt\tk\td\n";
    std::uniform_int_distribution<Node> target(0, graph.n-1);
    unsigned random_sources=0, active_sources=0;
    for (Node s : pool) {
        bool random = random_sources < 64;
        if (!random && (active_sources >= 64 || !graph.side[1].degree(s))) continue;
        const auto d = full_distances(graph, s);
        if (random) {
            ++random_sources;
            for (int k : {2,4,6}) {
                std::set<Node> used;
                while (used.size() < std::min<Node>(64, graph.n)) used.insert(target(rng));
                for (Node t : used) emit(uniform,s,t,k,d[t]);
            }
        } else {
            ++active_sources;
            std::array<std::vector<Node>, 10> bins;
            for (Node t=0; t<graph.n; ++t) if (d[t]!=0)
                bins[d[t]<0 ? 9 : std::min(d[t],8)].push_back(t);
            for (int k : {2,4,6}) {
                // Five disjoint groups: short paths, boundary, near-negative,
                // longer finite paths and unreachable. Empty groups stay empty.
                auto pick = [&](int lo, int hi) {
                    std::vector<Node> candidates;
                    for (int b=lo;b<=hi;++b)
                        candidates.insert(candidates.end(),bins[b].begin(),bins[b].end());
                    unsigned count=std::min<size_t>(12,candidates.size());
                    for (unsigned i=0;i<count;++i) {
                        unsigned j=std::uniform_int_distribution<unsigned>(i,candidates.size()-1)(rng);
                        std::swap(candidates[i],candidates[j]);
                        Node t=candidates[i]; emit(stratified,s,t,k,d[t]);
                    }
                };
                if (k>=2) pick(1,k-1);
                pick(k,k); pick(k+1,k+1);
                if (k+2<=8) pick(k+2,8);
                pick(9,9);
            }
        }
        if (random_sources==64 && active_sources==64) break;
    }
    if (!uniform || !stratified || random_sources<64 || active_sources<1)
        throw std::runtime_error("insufficient benchmark data");
}
