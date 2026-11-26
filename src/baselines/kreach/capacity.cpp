// Lower-bound the payload of the exact sparse/packed K-Reach representation.
// Each witness combines actual paths through a hub; missing witnesses only weaken the bound.
#include "../../radius/graph.hpp"
#include <iomanip>
#include <iostream>
#include <numeric>
using namespace khop;

std::vector<char> cover(const Graph& g) {
    std::vector<char> used(g.n);
    const auto& out=g.side[1];
    for(Node u=0; u<g.n; ++u) {
        if(used[u]) continue;
        for(auto j=out.offsets[u]; j<out.offsets[u+1]; ++j) {
            Node v=out.neighbors[j];
            if(!used[v]) { used[u]=used[v]=1; break; }
        }
    }
    return used;
}

std::vector<int> ball(const Adjacency& a, Node hub, int h, const std::vector<char>& core,
                      std::vector<Node>& reached, std::vector<uint8_t>& distance) {
    const auto nodes=a.offsets.size()-1;
    distance.assign(nodes,255);
    reached.clear();
    reached.push_back(hub);
    distance[hub]=0;
    std::vector<int> counts(h+1);
    for(size_t i=0; i<reached.size(); ++i) {
        Node u=reached[i];
        auto depth=distance[u];
        counts[depth]+=core[u];
        if(depth==h) continue;
        for(auto j=a.offsets[u]; j<a.offsets[u+1]; ++j) {
            auto v=a.neighbors[j];
            if(distance[v]==255) {
                distance[v]=depth+1;
                reached.push_back(v);
            }
        }
    }
    std::partial_sum(counts.begin(),counts.end(),counts.begin());
    return counts;
}

int main(int argc, char** argv) {
    if(argc!=4) throw std::invalid_argument("capacity graph_name N graph.edges");
    // Reproduce the same deterministic vertex cover and row-layout decision as kreach.cpp.
    auto g=Graph::load(std::stoul(argv[2]),argv[3]);
    auto core=cover(g);
    uint64_t roots=std::accumulate(core.begin(),core.end(),uint64_t{0});
    uint64_t packed=(roots+3)/4;
    std::vector<Node> hubs(g.n);
    std::iota(hubs.begin(),hubs.end(),0);
    const auto& in=g.side[0]; const auto& out=g.side[1];
    auto score=[&](Node u) { return uint64_t(in.degree(u))*out.degree(u); };
    size_t limit=std::min<size_t>(32,g.n);
    std::partial_sort(hubs.begin(),hubs.begin()+limit,hubs.end(),[&](Node u,Node v){
        return score(u)!=score(v)?score(u)>score(v):u<v;
    });
    hubs.resize(limit);
    std::vector<uint32_t> lower4(g.n),lower6(g.n);
    std::vector<Node> reached;
    std::vector<uint8_t> distance;
    for(Node hub:hubs) {
        auto counts=ball(out,hub,4,core,reached,distance);
        ball(in,hub,4,core,reached,distance);
        for(Node u:reached) if(core[u]) {
            auto d=distance[u];
            // Subtract self unconditionally, which is safe even when u is absent from the forward ball.
            if(d<=4) lower4[u]=std::max(lower4[u],uint32_t(std::max(0,counts[4-d]-1)));
            if(d<=4) lower6[u]=std::max(lower6[u],uint32_t(std::max(0,counts[std::min(4,6-int(d))]-1)));
        }
    }
    for(auto [k,lower]:{std::pair<int,const std::vector<uint32_t>&>{4,lower4},{6,lower6}}) {
        uint64_t dense=0, payload=0, entries=0;
        for(Node u=0;u<g.n;++u) if(core[u]) {
            uint64_t bytes=4ull*lower[u]; entries+=lower[u]; dense+=bytes>=packed;
            payload+=std::min(bytes,packed);
        }
        std::cout<<argv[1]<<'\t'<<k<<'\t'<<roots<<'\t'<<hubs.size()<<'\t'
                 <<dense<<'\t'<<entries<<'\t'<<payload<<'\t'<<roots*packed<<'\n';
    }
}
