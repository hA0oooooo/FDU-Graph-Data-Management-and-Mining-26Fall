// Diagnose the frozen tables; do not select radii or train on any evaluation split.
#include "hotspot.hpp"
#include "filters.hpp"
#include "query_io.hpp"
#include "../benchmark_metrics.hpp"
#include <filesystem>
#include <iomanip>
#include <map>

using namespace khop;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;

HotIndex restore(const Graph& g,const fs::path& filename) {
    std::ifstream input(filename);
    std::string header; std::getline(input,header);
    if (header!="root\tin\tout") throw std::runtime_error("invalid configuration header");
    std::vector<Node> roots; Profiles profiles; Config radii;
    Node v; int hi,ho;
    while(input>>v>>hi>>ho) {
        if (v>=g.n || (!roots.empty() && v<=roots.back()) || std::min(hi,ho)<0 || std::max(hi,ho)>max_radius)
            throw std::runtime_error("invalid frozen root");
        roots.push_back(v);
        for(int dir:{0,1}) {
            int h=dir?ho:hi; radii.push_back(h);
            profiles.push_back(h?explore(g.side[dir],v,h):Profile{});
        }
    }
    if(!input.eof()) throw std::runtime_error("invalid configuration row");
    return HotIndex(profiles,radii,roots,g.n);
}
template<bool track, bool prune>
struct HotPolicy : PlainSearch {
    const HotIndex& idx;
    Count skipped=0;
    explicit HotPolicy(const HotIndex& index):idx(index) {}
    int decide(Node u,int dir,int j,int r,Node t) {
        int result=idx.decide(u,dir,j,r,t);
        if constexpr(track) skipped+=result<0;
        return prune?result:std::max(0,result);
    }
};
struct Counters { Count n=0,base=0,hot=0,positive=0,combo=0,skipped=0,forest=0,hot_yes=0,both=0; };

int main(int argc,char** argv) {
    if(argc!=6) throw std::runtime_error("hotspot_ablation N edges workload_dir fit_dir output");
    Graph g=Graph::load(std::stoul(argv[1]),argv[2]);
    Search search(g); fs::path work=argv[3],fit=argv[4],dest=argv[5];
    auto adaptive=restore(g,fit/"adaptive/radii.tsv");
    auto uniform=restore(g,fit/"uniform/radii.tsv");
    auto start=Clock::now();
    CoverTree tree(g);
    auto tree_s=std::chrono::duration<double>(Clock::now()-start).count();
    Count tree_bytes=sizeof(int)*tree.id.capacity()+sizeof(Node)*(tree.pre.capacity()+tree.post.capacity()+tree.depth.capacity());
    std::ofstream timing(dest/"timing.tsv"), stats(dest/"mechanism.tsv");
    timing<<"split\tmethod\tqueries\tbatch_ns\trepeats\taux_bytes\ttree_build_s\n";
    stats<<"split\tk\tclass\tqueries\tbase_scans\thot_scans\tpositive_only_scans\tcombo_scans\tbranches_pruned\ttree_yes\thot_yes\toverlap_yes\n";
    HotPolicy<false,false> positive(adaptive);
    for (std::string split:{"benchmark","benchmark-uniform","benchmark-stratified","test"}) {
        auto qs=load_queries(work/(split+".tsv"),g.n,-1);
        auto measure=[&](const char* name,auto fn,Count bytes,double build) {
            auto result=khop_bench::measure(qs.size(),[&](size_t i){return fn(qs[i]).yes;});
            for(size_t i=0;i<qs.size();++i) check(qs[i],{bool(result.answers[i]),'F',0});
            timing<<split<<'\t'<<name<<'\t'<<qs.size()<<'\t'<<result.median_ns<<'\t'<<result.repeats
                  <<'\t'<<bytes<<'\t'<<std::setprecision(12)<<build<<'\n';
        };
        measure("bibfs",[&](const Query& q){return search.run(q);},0,0);
        measure("tree",[&](const Query& q){return tree.witness(g,q)?Answer{true,'U',0}:search.run(q);},tree_bytes,tree_s);
        measure("uniform",[&](const Query& q){return uniform.query(search,q);},uniform.bytes(),0);
        measure("adaptive",[&](const Query& q){return adaptive.query(search,q);},adaptive.bytes(),0);
        measure("positive-only",[&](const Query& q){return adaptive.tables.empty()?search.run(q):search.guided(q,positive);},adaptive.bytes(),0);
        measure("tree-uniform",[&](const Query& q){return tree.witness(g,q)?Answer{true,'U',0}:uniform.query(search,q);},tree_bytes+uniform.bytes(),tree_s);
        measure("tree-adaptive",[&](const Query& q){return tree.witness(g,q)?Answer{true,'U',0}:adaptive.query(search,q);},tree_bytes+adaptive.bytes(),tree_s);
        std::map<std::pair<int,std::string>,Counters> groups;
        for(const Query& q:qs) {
            HotPolicy<true,true> instrumented(adaptive);
            auto a=search.guided(q,instrumented); auto pos=search.guided(q,positive); auto base=search.run(q);
            bool tree_yes=tree.witness(g,q);
            check(q,a); check(q,pos); check(q,base);
            if(tree_yes && !base.yes) throw std::logic_error("invalid tree witness");
            auto& c=groups[{q.k,q.d<0?"unreachable":q.d>q.k?"beyond":"within"}];
            ++c.n; c.base+=base.scans; c.hot+=a.scans; c.positive+=pos.scans;
            c.combo+=tree_yes?0:a.scans; c.skipped+=instrumented.skipped;
            c.forest+=tree_yes; c.hot_yes+=a.route=='U'; c.both+=tree_yes && a.route=='U';
        }
        for(auto& [key,c]:groups)
            stats<<split<<'\t'<<key.first<<'\t'<<key.second<<'\t'<<c.n<<'\t'<<c.base<<'\t'<<c.hot
                 <<'\t'<<c.positive<<'\t'<<c.combo<<'\t'<<c.skipped<<'\t'<<c.forest<<'\t'<<c.hot_yes<<'\t'<<c.both<<'\n';
    }
}
