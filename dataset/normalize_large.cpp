#include <algorithm>
#include <charconv>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 5) return 2;
    const bool gra = std::string(argv[1]) == "gra";
    const size_t expected_edges = std::stoull(argv[2]);
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);
    // Pack (source, target) so one numeric sort produces lexicographic edge order.
    std::vector<uint64_t> edges;
    edges.reserve(expected_edges);
    std::vector<int32_t> dense;
    std::string line;
    size_t declarations = 0, n_declared = 0;
    constexpr int32_t unseen = -1, present = -2;
    if (gra) {
        std::getline(std::cin, line);
        if (line != "graph_for_greach") throw std::runtime_error("GRAIL format");
        std::getline(std::cin, line);
        n_declared = std::stoul(line);
        dense.assign(n_declared, present);  // Includes declared isolated vertices.
    }
    while (std::getline(std::cin, line)) {
        if (!gra && (line.empty() || line[0] == '#')) continue;
        const char* p = line.data();
        const char* end = p + line.size();
        auto skip_space = [&]() {
            while (p < end && (*p == ' ' || *p == '\t' || *p == '\r')) ++p;
        };
        auto read_vertex = [&]() {
            skip_space();
            uint32_t v;
            auto x = std::from_chars(p, end, v);
            if (x.ec != std::errc() || v >= 100000000U || (gra && v >= n_declared))
                throw std::runtime_error("invalid vertex ID");
            p = x.ptr;
            if (v >= dense.size()) dense.resize(size_t(v) + 1, unseen);
            dense[v] = present;
            return v;
        };
        auto u = read_vertex();
        if (gra) {
            if (u != declarations++ || p == end || *p++ != ':')
                throw std::runtime_error("invalid row");
            skip_space();
            while (p < end && *p != '#') {
                edges.push_back((uint64_t(u) << 32) | read_vertex());
                skip_space();
            }
            if (p == end || *p++ != '#') throw std::runtime_error("unterminated row");
        } else {
            edges.push_back((uint64_t(u) << 32) | read_vertex());
        }
        skip_space();
        if (p != end) throw std::runtime_error("trailing data");
    }
    if (gra && (declarations != n_declared))
        throw std::runtime_error("missing declared vertices");
    const auto rows = edges.size();
    std::sort(edges.begin(), edges.end());
    edges.erase(std::unique(edges.begin(), edges.end()), edges.end());
    std::ofstream nodes(argv[4]), out(argv[3]);
    nodes.exceptions(std::ios::badbit | std::ios::failbit);
    out.exceptions(std::ios::badbit | std::ios::failbit);
    nodes << "dense_id\tsnap_id\n";  // Same two-column schema as the original loader.
    uint32_t n = 0;
    for (size_t id = 0; id < dense.size(); ++id) {
        if (dense[id] == present) {
            dense[id] = n++;
            nodes << dense[id] << '\t' << id << '\n';
        }
    }
    size_t loops = 0;
    std::vector<bool> incident(n);
    for (auto e : edges) {
        auto u = dense[e >> 32], v = dense[uint32_t(e)];
        out << u << '\t' << v << '\n';
        incident[u] = incident[v] = true;
        loops += u == v;
    }
    nodes.close();
    out.close();
    auto isolated = std::count(incident.begin(), incident.end(), false);
    std::cout << n << ' ' << rows << ' ' << edges.size() << ' ' << loops << ' ' << isolated
              << '\n';
}
