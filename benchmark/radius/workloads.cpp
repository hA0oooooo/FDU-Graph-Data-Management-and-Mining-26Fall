// Independent full single-source distances for the frozen workload oracle.
#include "../../src/radius/graph.hpp"
#include <filesystem>
#include <random>
#include <set>

using namespace khop;

std::vector<int> distances(const Graph& g, Node s) {
    std::vector<int> d(g.n,-1);
    std::vector<Node> queue{s};
    d[s]=0;
    const auto& a=g.side[1];
    for (size_t i=0;i<queue.size();++i) {
        Node u=queue[i];
        for (auto j=a.offsets[u];j<a.offsets[u+1];++j) {
            Node v=a.neighbors[j];
            if (d[v]!=-1) continue;
            d[v]=d[u]+1; queue.push_back(v);
        }
    }
    return d;
}

void sample_source(const Graph& g, Node s, std::mt19937& rng, std::vector<Query>& rows) {
    auto d=distances(g,s);
    // 1..7 exact; 8 pools all larger finite distances; 9/10 split unreachable
    // targets according to whether they have an incoming edge.
    std::array<std::vector<Node>,11> buckets;
    for (Node t=0;t<g.n;++t) if (s!=t) {
        int bin=d[t]<0 ? 9+int(g.side[0].degree(t)>0) : std::min(d[t],8);
        buckets[bin].push_back(t);
    }
    for (int k:{2,4,6}) {
        std::set<Node> used;
        auto pick=[&](int lo,int hi) {
            size_t total=0;
            for (int i=lo;i<=hi;++i) total+=buckets[i].size();
            if (!total) return;
            size_t pos=std::uniform_int_distribution<size_t>(0,total-1)(rng);
            for (int i=lo;i<=hi;++i) {
                if (pos<buckets[i].size()) {
                    Node t=buckets[i][pos];
                    if (used.insert(t).second) rows.push_back({s,t,k,d[t]});
                    return;
                }
                pos-=buckets[i].size();
            }
        };
        pick(1,k-1); pick(k,k); pick(k+1,k+1); pick(k+2,8); pick(9,9); pick(10,10);
    }
}

int main(int argc,char** argv) {
    if (argc<5 || argc>7) throw std::runtime_error("workloads N graph.edges excluded.txt output [confirm [seed]]");
    bool confirm=argc>=6 && std::string(argv[5])=="confirm";
    if (argc>=6 && !confirm) throw std::runtime_error("expected confirm");
    Graph g=Graph::load(std::stoul(argv[1]),argv[2]);
    std::ifstream exclusion(argv[3]);
    if (!exclusion) throw std::runtime_error("missing exclusion file");
    std::set<Node> used;
    Node s;
    while (exclusion>>s) used.insert(s);
    std::vector<Node> pool(g.n);
    std::iota(pool.begin(),pool.end(),0);
    std::mt19937 rng(argc==7?std::stoul(argv[6]):(confirm?27112026:25112026));
    std::shuffle(pool.begin(),pool.end(),rng);
    bool stress=g.n>=1000000 || g.side[1].neighbors.size()>=10000000;
    std::filesystem::create_directories(argv[4]);
    std::vector<std::string> names=confirm?std::vector<std::string>{"holdout-1","holdout-2","holdout-3"}
                                          :std::vector<std::string>{"train","validation","test"};
    for (const auto& split:names) {
        int active=0,sinks=0;
        std::vector<Query> rows;
        for (Node u:pool) {
            if (used.count(u)) continue;
            bool has_edges=g.side[1].degree(u)>0;
            int& count=has_edges?active:sinks;
            int limit=has_edges?(stress?6:24):(stress?2:4);
            if (count>=limit) continue;
            ++count; used.insert(u); sample_source(g,u,rng,rows);
            if (active==(stress?6:24) && sinks==(stress?2:4)) break;
        }
        std::shuffle(rows.begin(),rows.end(),rng);
        std::ofstream out(std::filesystem::path(argv[4])/(split+".tsv"));
        out<<"s\tt\tk\td\n";
        for (auto q:rows) out<<q.s<<'\t'<<q.t<<'\t'<<q.k<<'\t'<<q.d<<'\n';
        if (!out || rows.empty()) throw std::runtime_error("empty/failed workload");
    }
}
