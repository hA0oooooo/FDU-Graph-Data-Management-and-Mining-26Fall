#include "../../benchmark_metrics.hpp"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <vector>
#ifdef _OPENMP
#include <omp.h>
#endif

using Adj = std::vector<std::vector<int>>;
using Clock = std::chrono::steady_clock;
using Nanoseconds = std::chrono::nanoseconds;

// Each covered pair has four possible states: three tiers and unreachable.
// Sparse rows store rank+tier; dense rows pack four states per byte.
struct CoreRow {
    std::vector<uint32_t> sparse;
    std::vector<uint8_t> packed;

    void finish(size_t roots) {
        if (sparse.size() * sizeof(uint32_t) < (roots + 3) / 4) {
            std::sort(sparse.begin(), sparse.end());
            sparse.shrink_to_fit();
            return;
        }
        packed.assign((roots + 3) / 4, 0xff);
        for (uint32_t value : sparse) {
            const uint32_t rank = value >> 2, shift = 2 * (rank & 3);
            auto& byte = packed[rank >> 2];
            byte = (byte & ~(3u << shift)) | ((value & 3u) << shift);
        }
        std::vector<uint32_t>().swap(sparse);
    }

    unsigned tier(uint32_t rank) const {
        if (!packed.empty()) return (packed[rank >> 2] >> (2 * (rank & 3))) & 3u;
        const uint32_t key = rank << 2;
        auto it = std::lower_bound(sparse.begin(), sparse.end(), key);
        return it != sparse.end() && (*it >> 2) == rank ? *it & 3u : 3u;
    }

    uint64_t bytes() const {
        return packed.capacity() + sizeof(uint32_t) * sparse.capacity();
    }
};

struct KReach {
    const Adj &out, &in;
    int k;
    std::vector<bool> covered;
    std::vector<CoreRow> rows;
    std::vector<int> rank;
    uint64_t index_bytes = 0;
    uint64_t entries = 0, bfs_scans = 0;
    int roots = 0;

    KReach(const Adj& out, const Adj& in, int k, int threads=1)
        : out(out), in(in), k(k), covered(out.size()), rank(out.size(), -1) {
        // Take endpoints of every first uncovered edge in a deterministic order.
        for (int u = 0; u < static_cast<int>(out.size()); ++u) {
            if (covered[u]) continue;
            for (int v : out[u]) {
                if (!covered[v]) {
                    covered[u] = covered[v] = true;
                    break;
                }
            }
        }

        for (size_t u = 0; u < covered.size(); ++u)
            if (covered[u]) rank[u] = roots++;
        rows.resize(roots);
        std::cerr << "cover roots=" << roots << "\n";
        int completed = 0;
        #ifdef _OPENMP
        omp_set_dynamic(0);
        #else
        if (threads != 1) throw std::invalid_argument("parallel construction requires OpenMP");
        #endif
        #pragma omp parallel num_threads(threads)
        {
            std::vector<int> visited(out.size(), -1), depth(out.size()), queue;
            queue.reserve(out.size());
            #pragma omp for schedule(dynamic, 1)
            for (int root = 0; root < static_cast<int>(out.size()); ++root) {
                if (!covered[root]) continue;
                auto& row = rows[rank[root]];
                queue.clear();
                queue.push_back(root);
                visited[root] = root;
                depth[root] = 0;
                uint64_t scans = 0;
                for (size_t i = 0; i < queue.size(); ++i) {
                    const int u = queue[i];
                    if (depth[u] == k) break;
                    scans += out[u].size();
                    for (int v : out[u]) {
                        if (visited[v] == root) continue;
                        visited[v] = root;
                        depth[v] = depth[u] + 1;
                        queue.push_back(v);
                        if (covered[v]) {
                            const unsigned tier = std::max(0, depth[v] - (k - 2));
                            row.sparse.push_back((uint32_t(rank[v]) << 2) | tier);
                        }
                    }
                }
                uint64_t row_entries = row.sparse.size();
                row.finish(roots);
                #pragma omp critical(kreach_progress)
                {
                    entries += row_entries;
                    bfs_scans += scans;
                    index_bytes += row.bytes();
                    ++completed;
                    if (completed % 1024 == 0 || completed == roots)
                        std::cerr << "roots=" << completed << "/" << roots << " payload_bytes="
                                  << index_bytes << " entries=" << entries << "\n";
                }
            }
        }
    }

    bool core(int u, int v, int endpoint_hops) const {
        if (u == v) return true;  // Implicit zero-length core, k >= 2.
        return rows[rank[u]].tier(rank[v]) <= unsigned(2 - endpoint_hops);
    }

    bool query(int s, int t) const {
        if (s == t) return true;
        if (covered[s] && covered[t]) return core(s, t, 0);
        if (covered[s]) {
            for (int v : in[t]) if (core(s, v, 1)) return true;
        } else if (covered[t]) {
            for (int u : out[s]) if (core(u, t, 1)) return true;
        } else {
            for (int u : out[s])
                for (int v : in[t])
                    if (core(u, v, 2)) return true;
        }
        return false;
    }
};

struct Query { int s, t; bool truth; };

int main(int argc, char** argv) {
    if (argc < 5 || argc > 7) {
        std::cerr << "usage: kreach N EDGES WORKLOAD K [answer-file [build-threads]]\n";
        return 2;
    }
    const int n = std::stoi(argv[1]), k = std::stoi(argv[4]);
    const int threads = argc==7 ? std::stoi(argv[6]) : 1;
    if (n < 0 || n > (1 << 30) || k < 2 || threads<1)
        throw std::invalid_argument("requires 0 <= N <= 2^30 and K >= 2");
    Adj out(n), in(n);
    std::ifstream graph(argv[2]), workload(argv[3]);
    if (!graph || !workload) throw std::runtime_error("cannot open input");
    int s, t, query_k, d;
    while (graph >> s >> t) {
        out.at(s).push_back(t);
        in.at(t).push_back(s);
    }
    std::string header;
    std::getline(workload, header);
    std::vector<Query> queries;
    while (workload >> s >> t >> query_k >> d) {
        if (query_k == k) queries.push_back({s, t, 0 <= d && d <= k});
    }
    if (queries.empty()) throw std::runtime_error("no queries with requested K");

    const auto start = Clock::now();
    KReach index(out, in, k,threads);
    const auto build_ns = std::chrono::duration_cast<Nanoseconds>(Clock::now() - start).count();
    uint64_t ready=khop_bench::rss_kib();
    int errors = 0, positives = 0, cases[4] = {};
    for (const auto& q : queries) {
        ++cases[2 * !index.covered[q.s] + !index.covered[q.t]];
        positives += q.truth;
    }
    auto timing=khop_bench::measure(queries.size(),[&](size_t i){
        return index.query(queries[i].s,queries[i].t);
    });
    const auto& answers=timing.answers;
    for(size_t i=0;i<queries.size();++i)errors+=answers[i]!=queries[i].truth;
    if (argc>=6) {
        std::ofstream file(argv[5]);
        file<<"answer\n";
        for(uint8_t answer:answers) file<<int(answer)<<'\n';
    }
    uint64_t allocated=index.index_bytes+index.rows.capacity()*sizeof(CoreRow)
        +index.rank.capacity()*sizeof(int)+(index.covered.capacity()+7)/8;
    rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    std::cout << k << '\t' << index.roots << '\t' << index.entries << '\t'
              << index.bfs_scans << '\t' << build_ns << '\t' << usage.ru_maxrss << '\t'
              << queries.size() << '\t' << positives << '\t' << errors << '\t'
              << timing.first_ns << '\t' << timing.median_ns;
    for (int count : cases) std::cout << '\t' << count;
    std::cout << '\t' << index.index_bytes << '\t' << timing.repeats << '\t' << ready << '\t' << allocated << '\n';
    return errors ? 1 : 0;
}
