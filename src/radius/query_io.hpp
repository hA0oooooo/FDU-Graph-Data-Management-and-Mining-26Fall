#pragma once
#include "graph.hpp"
#include <filesystem>

namespace khop {
inline std::vector<Query> load_queries(const std::filesystem::path& path,Node n,int fixed_k) {
    std::ifstream f(path);
    std::string header; std::getline(f,header);
    if (header!="s\tt\tk\td") throw std::runtime_error("invalid TSV "+path.string());
    std::vector<Query> qs;
    Query q;
    while (f>>q.s>>q.t>>q.k>>q.d) {
        if (q.s>=n || q.t>=n || q.k<0 || q.d < -1) throw std::runtime_error("invalid query");
        if (fixed_k<0 || fixed_k==q.k) qs.push_back(q);
    }
    if (!f.eof() || qs.empty()) throw std::runtime_error("unreadable workload");
    return qs;
}
inline void check(const Query& q,Answer a) {
    if (a.yes!=(q.d>=0 && q.d<=q.k))
        throw std::runtime_error("wrong answer at "+std::to_string(q.s)+","+std::to_string(q.t)+","+std::to_string(q.k));
}
}
