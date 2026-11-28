#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace khop {
using Node = uint32_t;
using Count = uint64_t;

struct Adjacency {
    std::vector<uint32_t> offsets;
    std::vector<Node> neighbors;
    unsigned degree(Node v) const { return offsets[v+1] - offsets[v]; }
};

struct Graph {
    std::array<Adjacency,2> side;  // 0 follows incoming edges, 1 outgoing
    Node n;
    Graph(Node nodes, const std::vector<std::pair<Node,Node>>& edges): n(nodes) {
        if (edges.size() >= std::numeric_limits<uint32_t>::max()) throw std::length_error("CSR limit");
        for (auto& adj: side) adj.offsets.assign(n+1,0);
        for (auto [u,v]: edges) {
            if (u>=n || v>=n) throw std::runtime_error("edge outside vertex range");
            ++side[0].offsets[v+1]; ++side[1].offsets[u+1];
        }
        for (auto& adj: side) {
            std::partial_sum(adj.offsets.begin(),adj.offsets.end(),adj.offsets.begin());
            adj.neighbors.resize(edges.size());
        }
        auto in=side[0].offsets, out=side[1].offsets;
        for (auto [u,v]: edges) {
            side[0].neighbors[in[v]++]=u;
            side[1].neighbors[out[u]++]=v;
        }
    }
    static Graph load(Node n, const std::string& path) {
        std::ifstream f(path);
        if (!f) throw std::runtime_error("cannot open "+path);
        std::vector<std::pair<Node,Node>> edges;
        Node u,v;
        while (f>>u>>v) edges.emplace_back(u,v);
        if (!f.eof()) throw std::runtime_error("invalid edge row");
        return Graph(n,edges);
    }
};

struct Query { Node s,t; int k,d; };
struct Answer { bool yes; char route; Count scans; };

struct PlainSearch {
    int decide(Node, int, int, int, Node) const { return 0; }
    void scanned(Node, int, int, int, Count) const {}
};

class Search {
    const Graph& g;
    std::array<std::vector<uint32_t>,2> seen;
    std::array<std::vector<Node>,2> frontier;
    std::vector<Node> next;
    uint32_t epoch=0;
public:
    explicit Search(const Graph& graph):g(graph) { for (auto& v:seen) v.resize(g.n); }

    Answer run(const Query& q, bool both=true) {
        PlainSearch policy;
        return guided(q, policy, both);
    }

    // A positive decision supplies a path, a negative one closes only this row.
    template<class Policy>
    Answer guided(const Query& q, Policy& policy, bool both=true) {
        if (q.k<0) throw std::invalid_argument("negative k");
        if (q.s==q.t || q.k==0) return {q.s==q.t,'T',0};
        if (!g.side[1].degree(q.s) || !g.side[0].degree(q.t)) return {false,'T',0};
        if (++epoch==0) {
            for (auto& v:seen) std::fill(v.begin(),v.end(),0);
            ++epoch;
        }
        frontier[0].assign(1,q.t); frontier[1].assign(1,q.s);
        seen[0][q.t]=seen[1][q.s]=epoch;
        Count work[2]={g.side[0].degree(q.t),g.side[1].degree(q.s)};
        Count scans=0;
        int depth[2]={0,0};
        for (int step=0;step<q.k;++step) {
            int dir=both && work[0]<work[1] ? 0:1;
            if (!work[dir]) break;
            const auto& adj=g.side[dir];
            next.clear(); work[dir]=0;
            int j=depth[dir]++;
            int remaining=q.k-j;
            for (Node u:frontier[dir]) {
                int decision = j ? policy.decide(u,dir,j,remaining,dir?q.t:q.s) : 0;
                if (decision>0) return {true,'U',scans};
                if (decision<0) continue;
                Count before=scans;
                for (auto i=adj.offsets[u];i<adj.offsets[u+1];++i) {
                    Node v=adj.neighbors[i]; ++scans;
                    if (seen[1-dir][v]==epoch) {
                        policy.scanned(u,dir,j,remaining,scans-before);
                        return {true,'F',scans};
                    }
                    if (seen[dir][v]!=epoch) {
                        seen[dir][v]=epoch; next.push_back(v);
                        work[dir]+=adj.degree(v);
                    }
                }
                policy.scanned(u,dir,j,remaining,scans-before);
            }
            next.swap(frontier[dir]);
        }
        return {false,'F',scans};
    }
};
}
