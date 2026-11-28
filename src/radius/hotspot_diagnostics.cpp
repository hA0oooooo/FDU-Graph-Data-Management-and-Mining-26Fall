// Measure complete-layer build work and opportunities on unpruned training/validation traces.
#include "query_io.hpp"
#include "index.hpp"
#include <filesystem>
#include <iostream>

using namespace khop;
namespace fs=std::filesystem;
struct Opportunity : PlainSearch {
    const std::vector<Node>& roots;
    int reverse_depth=0;
    size_t width=0;
    Count total=0;
    std::vector<int> demanded;
    struct Bin {Count visits=0,edges=0,probes=0;};
    std::array<std::array<Bin,3>,2> eligible{};
    explicit Opportunity(const std::vector<Node>& candidates):roots(candidates),demanded(2*candidates.size()) {}
    void scanned(Node u,int dir,int j,int r,Count a) {
        total+=a;
        if (!j) return;
        auto it=std::lower_bound(roots.begin(),roots.end(),u);
        if (it==roots.end() || *it!=u) return;
        auto& max_r=demanded[2*(it-roots.begin())+dir];
        if (a) max_r=std::max(max_r,r);
        for(int h=1;h<=3;++h) {
            // The extra opportunity requires a smaller gap and a cheap layer to test.
            if(r<=h || r-reverse_depth>h || width>8 || width>=a) continue;
            auto& bin=eligible[dir][h-1];
            ++bin.visits; bin.edges+=a; bin.probes+=width;
        }
    }
};
int main(int argc,char** argv) {
    if(argc!=6) throw std::runtime_error("hotspot_diagnostics N edges workload_dir frozen_radii.tsv profile_output.tsv");
    Graph g=Graph::load(std::stoul(argv[1]),argv[2]); Search search(g);
    std::ifstream config(argv[4]); std::string header; std::getline(config,header);
    if(header!="root\tin\tout")throw std::runtime_error("invalid frozen configuration");
    std::vector<Node> roots; Config chosen; Node v;int a,b;
    while(config>>v>>a>>b) {
        if(v>=g.n || std::min(a,b)<0 || std::max(a,b)>max_radius)
            throw std::runtime_error("invalid frozen root");
        roots.push_back(v); chosen.push_back(a); chosen.push_back(b);
    }
    if(!config.eof() || !std::is_sorted(roots.begin(),roots.end()))throw std::runtime_error("invalid root list");
    std::cout<<"split\tdir\th\tvisits\toriginal_row_scans\tfrontier_probes\ttotal_scans\n";
    for(const std::string split:{"train","validation"}) {
        Opportunity trace(roots);
        auto qs=load_queries(fs::path(argv[3])/(split+".tsv"),g.n,-1);
        for(const auto& q:qs) {
            auto before=trace.total;
            auto result=search.observe_layers(q,trace,true,[&](int,int,int b,size_t n){trace.reverse_depth=b;trace.width=n;});
            check(q,result);
            if(trace.total-before!=result.scans)throw std::logic_error("trace scan accounting");
        }
        if (split=="train") {
            std::ofstream out(argv[5]);
            if (!out) throw std::runtime_error("cannot write profile output");
            out<<"root\tdir\tmax_demand\tchosen_h\tfull_scans\tglobal_cap_scans\tdemand_cap_scans\tchosen_scans\n";
            for(size_t i=0;i<chosen.size();++i) {
                const auto profile=explore(g.side[i%2],roots[i/2],max_radius);
                const int limit=std::min(trace.demanded[i],max_radius);
                if (chosen[i]>limit) throw std::logic_error("selected radius exceeds training demand");
                const auto capped=limit?explore(g.side[i%2],roots[i/2],limit):Profile{};
                if (limit) {
                    if (profile.dist.size()!=capped.dist.size()) throw std::logic_error("different vertex sets");
                    for (Node u=0;u<g.n;++u)
                        if (std::min<int>(profile.dist[u],limit+1)!=std::min<int>(capped.dist[u],limit+1))
                            throw std::logic_error("capped distance differs");
                    for (int h=0;h<=limit;++h)
                        if (profile.entries[h]!=capped.entries[h] || profile.scans[h]!=capped.scans[h])
                            throw std::logic_error("capped layer differs");
                }
                const Count cap_scans=std::accumulate(capped.scans.begin(),capped.scans.end(),Count(0));
                const auto scans=[&](int h) {
                    return std::accumulate(profile.scans.begin(),profile.scans.begin()+h+1,Count(0));
                };
                out<<roots[i/2]<<'\t'<<(i%2?"out":"in")<<'\t'<<trace.demanded[i]<<'\t'<<chosen[i]
                   <<'\t'<<scans(max_radius)<<'\t'<<scans(max_radius-1)<<'\t'<<cap_scans
                   <<'\t'<<scans(chosen[i])<<'\n';
            }
        }
        for(int dir:{0,1})for(int h=1;h<=3;++h) {
            auto bin=trace.eligible[dir][h-1];
            std::cout<<split<<'\t'<<(dir?"out":"in")<<'\t'<<h<<'\t'<<bin.visits<<'\t'<<bin.edges<<'\t'
                     <<bin.probes<<'\t'<<trace.total<<'\n';
        }
    }
}
