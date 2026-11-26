#include "../../benchmark_metrics.hpp"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <queue>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <utility>
#include <vector>

using Adj = std::vector<std::vector<int>>;
using Clock = std::chrono::steady_clock;
constexpr int INF = std::numeric_limits<int>::max() / 2;

struct Label {
    std::vector<uint8_t> bytes;
    int last = 0;

    void append_number(unsigned value) {
        while (value >= 128) {
            bytes.push_back(static_cast<uint8_t>((value & 127) | 128));
            value >>= 7;
        }
        bytes.push_back(static_cast<uint8_t>(value));
    }

    void append(int rank, int distance) {
        append_number(rank - last);
        append_number(distance);
        last = rank;
    }
};

struct Cursor {
    const std::vector<uint8_t>& bytes;
    size_t position = 0;
    int rank = 0, distance = 0;
    explicit Cursor(const Label& label) : bytes(label.bytes) {}

    unsigned read_number() {
        unsigned value = 0;
        for (int shift = 0;; shift += 7) {
            unsigned byte = bytes[position++];
            value |= (byte & 127) << shift;
            if (byte < 128) return value;
        }
    }

    bool next() {
        if (position == bytes.size()) return false;
        rank += read_number();
        distance = read_number();
        return true;
    }
};

std::vector<int> root_order(const Adj& out, const Adj& in, bool use_cover) {
    const int n = out.size();
    std::vector<int> degree(n), roots;
    for (int u = 0; u < n; ++u) degree[u] = out[u].size() + in[u].size();
    if (!use_cover) {
        roots.resize(n);
        std::iota(roots.begin(), roots.end(), 0);
        std::sort(roots.begin(), roots.end(), [&](int a, int b) {
            return degree[a] != degree[b] ? degree[a] > degree[b] : a < b;
        });
        return roots;
    }
    // A loop is one incident edge. Opposite directed arcs are two edges.
    std::priority_queue<std::pair<int,int>> candidates;
    for (int u = 0; u < n; ++u) {
        degree[u] -= std::count(out[u].begin(), out[u].end(), u);
        if (degree[u]) candidates.emplace(degree[u], -u);
    }
    while (!candidates.empty()) {
        auto [old_degree, negative_id] = candidates.top();
        candidates.pop();
        int u = -negative_id;
        if (degree[u] != old_degree) continue;
        roots.push_back(u);
        degree[u] = 0;
        for (const auto* neighbors : {&out[u], &in[u]}) {
            for (int v : *neighbors) {
                if (degree[v] > 0 && --degree[v] > 0) candidates.emplace(degree[v], -v);
            }
        }
    }
    return roots;
}

struct Index {
    const Adj &out, &in;
    std::vector<Label> out_labels, in_labels;
    std::vector<char> out_receiver, in_receiver;
    std::vector<int> order;
    int64_t entries = 0, scans = 0, visited = 0, redundant = 0;

    Index(const Adj& forward, const Adj& reverse, const std::string& method, int threshold, bool materialize=true)
        : out(forward), in(reverse), out_labels(out.size()), in_labels(out.size()),
          out_receiver(out.size()), in_receiver(out.size()),
          order(root_order(out, in, method != "pll")) {
        for (int v : order) out_receiver[v] = in_receiver[v] = 1;
        if (method.find("plus") != std::string::npos) {
            for (size_t v = 0; v < out.size(); ++v) {
                if (static_cast<int>(out[v].size()) > threshold) out_receiver[v] = 1;
                if (static_cast<int>(in[v].size()) > threshold) in_receiver[v] = 1;
            }
        }
        if (!materialize) return;
        const bool strict = method.find("strict") != std::string::npos;
        const bool prune = !strict && method.find("full") == std::string::npos;
        std::vector<int> root_leg(order.size(), INF), seen(out.size(), -1);
        std::vector<int> queue(out.size()), depth(out.size());
        for (int rank = 0; rank < static_cast<int>(order.size()); ++rank) {
            const int hub = order[rank];
            if (rank == 0 || rank % 1024 == 0) {
                rusage usage{};
                getrusage(RUSAGE_SELF, &usage);
                std::cerr << "roots=" << rank << "/" << order.size()
                          << " labels=" << entries << " peak_kib=" << usage.ru_maxrss << "\n";
            }
            for (int back = 0; back < 2; ++back) {
                const auto& adj = back ? in : out;
                const auto& eligible = back ? out_receiver : in_receiver;
                auto& labels = back ? out_labels : in_labels;
                const Label& root_label = back ? in_labels[hub] : out_labels[hub];
                if (!strict) {
                    for (Cursor c(root_label); c.next() && c.rank < rank;) root_leg[c.rank] = c.distance;
                }
                const int visit_id = 2 * rank + back;
                queue[0] = hub;
                depth[hub] = 0;
                seen[hub] = visit_id;
                int head = 0, tail = 1;
                while (head < tail) {
                    const int u = queue[head++], d = depth[u];
                    ++visited;
                    if (eligible[u]) {
                        bool covered = false;
                        if (!strict) {
                            for (Cursor c(labels[u]); c.next() && c.rank < rank;) {
                                if (root_leg[c.rank] <= d - c.distance) {
                                    covered = true;
                                    break;
                                }
                            }
                        }
                        if (covered) {
                            ++redundant;
                            if (prune) continue;
                        } else {
                            labels[u].append(rank, d);
                            ++entries;
                        }
                    }
                    scans += adj[u].size();
                    for (int v : adj[u]) {
                        if (seen[v] == visit_id) continue;
                        seen[v] = visit_id;
                        depth[v] = d + 1;
                        queue[tail++] = v;
                    }
                }
                if (!strict) {
                    for (Cursor c(root_label); c.next() && c.rank < rank;) root_leg[c.rank] = INF;
                }
            }
        }
    }

    uint64_t allocated_bytes() const {
        uint64_t bytes=(out_labels.capacity()+in_labels.capacity())*sizeof(Label)
            +out_receiver.capacity()+in_receiver.capacity()+order.capacity()*sizeof(int);
        for(const auto* labels:{&out_labels,&in_labels})
            for(const auto& row:*labels)bytes+=row.bytes.capacity();
        return bytes;
    }

    bool labels_within(int s, int t, int k) const {
        if (s == t) return k >= 0;
        if (k < 1) return false;
        Cursor left(out_labels[s]), right(in_labels[t]);
        bool l = left.next(), r = right.next();
        while (l && r) {
            if (left.rank == right.rank) {
                if (left.distance <= k - right.distance) return true;
                l = left.next(); r = right.next();
            } else if (left.rank < right.rank) l = left.next();
            else r = right.next();
        }
        return false;
    }

    bool query(int s, int t, int k) const {
        if (s == t) return k >= 0;
        if (k <= 0) return false;
        if (out_receiver[s] && in_receiver[t]) return labels_within(s,t,k);
        if (out_receiver[s]) {
            for (int v : in[t]) if (labels_within(s,v,k-1)) return true;
        } else if (in_receiver[t]) {
            for (int u : out[s]) if (labels_within(u,t,k-1)) return true;
        } else {
            for (int u : out[s]) for (int v : in[t]) if (labels_within(u,v,k-2)) return true;
        }
        return false;
    }
};

struct Query { int s, t, k; };
int main(int argc, char** argv) {
    if (argc != 6) throw std::invalid_argument("method vertex-count edges queries degree-threshold");
    int n = std::stoi(argv[2]), threshold = std::stoi(argv[5]);
    Adj out(n), in(n);
    std::ifstream edges(argv[3]), requests(argv[4]);
    if (!edges || !requests) throw std::runtime_error("missing input");
    int u,v,k;
    while (edges >> u >> v) {
        out.at(u).push_back(v);
        in.at(v).push_back(u);
    }
    std::vector<Query> queries;
    while (requests >> u >> v >> k) queries.push_back({u,v,k});
    auto start = Clock::now();
    Index index(out, in, argv[1], threshold);
    auto built = Clock::now();
    uint64_t ready=khop_bench::rss_kib();
    auto timing=khop_bench::measure(queries.size(),[&](size_t i){
        const auto& q=queries[i];
        return index.query(q.s,q.t,q.k);
    });
    std::string predictions;
    for(auto value:timing.answers)predictions.push_back('0'+value);
    int64_t bytes = 0, capacity = 0;
    for (const auto* labels : {&index.out_labels, &index.in_labels}) {
        for (const auto& row : *labels) { bytes += row.bytes.size(); capacity += row.bytes.capacity(); }
    }
    rusage usage{};
    getrusage(RUSAGE_SELF, &usage);
    auto ns = [](auto a, auto b) { return std::chrono::duration_cast<std::chrono::nanoseconds>(b-a).count(); };
    std::cout << "{\"hubs\":" << index.order.size() << ",\"labels\":" << index.entries
              << ",\"encoded_bytes\":" << bytes << ",\"vector_capacity_bytes\":" << capacity
              << ",\"build_scans\":" << index.scans << ",\"popped_vertices\":" << index.visited
              << ",\"witnessed_candidates\":" << index.redundant << ",\"build_ns\":" << ns(start,built)
              << ",\"query_ns\":" << timing.first_ns << ",\"median_query_ns\":" << timing.median_ns
              << ",\"query_repeats\":" << timing.repeats << ",\"ready_rss_kib\":" << ready
              << ",\"index_allocated_bytes\":" << index.allocated_bytes() << ",\"process_peak_kib\":" << usage.ru_maxrss
              << ",\"predictions\":\"" << predictions << "\"}\n";
}
