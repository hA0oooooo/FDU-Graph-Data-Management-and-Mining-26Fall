// Lower-bound the payload of the exact sparse/packed K-Reach representation.
// Each witness combines actual paths through a hub; missing witnesses only weaken the bound.
#include "../../radius/graph.hpp"
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
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

std::vector<uint32_t> partition_counts(const Graph& g, const std::vector<char>& core, int k, size_t limit) {
    std::vector<Node> hubs(g.n);
    std::iota(hubs.begin(),hubs.end(),0);
    const auto& in=g.side[0];
    const auto& out=g.side[1];
    auto score=[&](Node u) { return uint64_t(in.degree(u))*out.degree(u); };
    limit=std::min<size_t>(limit,g.n);
    std::partial_sort(hubs.begin(),hubs.begin()+limit,hubs.end(),[&](Node u,Node v) {
        return score(u)!=score(v)?score(u)>score(v):u<v;
    });
    hubs.resize(limit);
    const size_t parts=limit+1;
    std::vector<uint16_t> bucket(g.n,limit);
    std::vector<uint8_t> best(g.n,255), distance;
    std::vector<Node> reached;
    // Assign each covered destination to a single partition by its nearest witness.
    for(size_t i=0;i<hubs.size();++i) {
        ball(out,hubs[i],k,core,reached,distance);
        for(Node v:reached) if(core[v] && distance[v]<best[v]) {
            bucket[v]=i;
            best[v]=distance[v];
        }
    }
    std::vector<int> rank(g.n,-1);
    size_t roots=0;
    for(Node v=0;v<g.n;++v) if(core[v]) rank[v]=roots++;
    std::vector<uint32_t> lower(roots*parts);
    std::vector<uint32_t> prefix((k+1)*parts);
    for(size_t i=0;i<hubs.size();++i) {
        std::fill(prefix.begin(),prefix.end(),0);
        ball(out,hubs[i],k,core,reached,distance);
        for(Node v:reached) if(core[v])
            ++prefix[size_t(distance[v])*parts+bucket[v]];
        for(int d=1;d<=k;++d) for(size_t b=0;b<parts;++b)
            prefix[size_t(d)*parts+b]+=prefix[size_t(d-1)*parts+b];
        ball(in,hubs[i],k,core,reached,distance);
        for(Node u:reached) if(core[u]) {
            uint32_t* row=lower.data()+size_t(rank[u])*parts;
            const uint32_t* count=prefix.data()+size_t(k-distance[u])*parts;
            for(size_t b=0;b<parts;++b) row[b]=std::max(row[b],count[b]);
        }
        if((i+1)%8==0 || i+1==hubs.size()) std::cerr<<"witnesses="<<i+1<<"/"<<hubs.size()<<'\n';
    }
    std::vector<uint32_t> result(g.n);
    for(Node u=0;u<g.n;++u) if(core[u]) {
        const auto* row=lower.data()+size_t(rank[u])*parts;
        uint32_t sum=std::accumulate(row,row+parts,uint32_t{0});
        result[u]=sum?sum-1:0;
    }
    return result;
}

int partition_main(int argc,char** argv) {
    if(argc==2 && std::string(argv[1])=="check") {
        std::mt19937 rng(26112026);
        uint64_t checked=0;
        for(Node n:{3,12,50}) for(int i=0;i<40;++i) {
            std::vector<std::pair<Node,Node>> edges;
            for(Node u=0;u<n;++u) for(Node v=0;v<n;++v) if(rng()%5==0)edges.emplace_back(u,v);
            Graph g(n,edges);
            auto core=cover(g);
            for(int k:{2,4,6}) {
                auto low=partition_counts(g,core,k,8);
                std::vector<Node> reached;
                std::vector<uint8_t> distance;
                for(Node u=0;u<n;++u) if(core[u]) {
                    auto exact=ball(g.side[1],u,k,core,reached,distance);
                    if(low[u]>uint32_t(exact.back()-1)) throw std::logic_error("invalid partition lower bound");
                    ++checked;
                }
            }
        }
        std::cout<<checked<<" row bounds verified\n";
        return 0;
    }
    if(argc!=6)throw std::invalid_argument("partition_capacity graph N edges k witness_count");
    auto g=Graph::load(std::stoul(argv[2]),argv[3]);
    int k=std::stoi(argv[4]);
    size_t hubs=std::stoul(argv[5]);
    if(k<1 || k>=255 || hubs<1 || hubs>=65535)throw std::invalid_argument("invalid witness parameters");
    auto core=cover(g);
    auto lower=partition_counts(g,core,k,hubs);
    uint64_t roots=std::accumulate(core.begin(),core.end(),uint64_t{0}),packed=(roots+3)/4;
    uint64_t payload=0,entries=0,dense=0;
    for(Node u=0;u<g.n;++u) if(core[u]) {
        uint64_t bytes=4ull*lower[u];
        entries+=lower[u];dense+=bytes>=packed;payload+=std::min(bytes,packed);
    }
    std::cout<<argv[1]<<'\t'<<k<<'\t'<<roots<<'\t'<<hubs<<'\t'<<dense<<'\t'<<entries<<'\t'<<payload<<'\t'<<roots*packed<<'\n';
    return 0;
}

int main(int argc, char** argv) {
    if(argc==2 || argc==6) return partition_main(argc,argv);
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
