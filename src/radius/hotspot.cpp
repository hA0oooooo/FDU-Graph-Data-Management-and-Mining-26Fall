#include "hotspot.hpp"
#include "filters.hpp"
#include "query_io.hpp"
#include "../benchmark_metrics.hpp"
#include <chrono>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <set>

using namespace khop;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
using Bins=std::array<Count,max_radius+1>;

double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now()-start).count();
}
struct RootTrace : PlainSearch {
    std::vector<Count> edges;
    explicit RootTrace(Node n):edges(n) {}
    void scanned(Node u,int,int j,int,Count a) { if(j) edges[u]+=a; }
};
std::vector<Node> choose_roots(const Graph& g,Search& search,const std::vector<Query>& train) {
    RootTrace trace(g.n);
    for (const Query& q:train) check(q,search.guided(q,trace));
    std::vector<Node> ids(g.n);
    std::iota(ids.begin(),ids.end(),0);
    ids.erase(std::remove_if(ids.begin(),ids.end(),[&](Node u){return !trace.edges[u];}),ids.end());
    auto end=ids.begin()+std::min<size_t>(12,ids.size());
    std::partial_sort(ids.begin(),end,ids.end(),[&](Node a,Node b){
        return trace.edges[a]!=trace.edges[b]?trace.edges[a]>trace.edges[b]:a<b;
    });
    ids.erase(end,ids.end());
    std::sort(ids.begin(),ids.end());
    return ids;
}

struct Histogram : PlainSearch {
    const std::vector<Node>& roots;
    std::vector<Bins> scans,visits;
    std::vector<std::array<std::set<Node>,max_radius+1>> sources;
    Node source=0;
    Count total=0;
    explicit Histogram(const std::vector<Node>& ids):roots(ids),scans(2*ids.size()),
        visits(scans.size()),sources(scans.size()) {}
    void scanned(Node u,int dir,int j,int r,Count a) {
        total+=a;
        if (!j) return;
        auto it=std::lower_bound(roots.begin(),roots.end(),u);
        if (it==roots.end() || *it!=u) return;
        size_t p=2*(it-roots.begin())+dir;
        scans[p].at(r)+=a;
        ++visits[p].at(r);
        sources[p].at(r).insert(source);
    }
};
Histogram histogram(Search& search,const std::vector<Query>& qs,const std::vector<Node>& roots) {
    Histogram hist(roots);
    for (const Query& q:qs) {
        hist.source=q.s;
        Count before=hist.total;
        auto a=search.guided(q,hist);
        check(q,a);
        if (hist.total-before!=a.scans) throw std::runtime_error("edge accounting mismatch");
    }
    return hist;
}
Profiles profiles(const Graph& g,const std::vector<Node>& roots,const Config& depths) {
    Profiles result;
    for (size_t i=0;i<depths.size();++i)
        result.push_back(depths[i]?explore(g.side[i%2],roots[i/2],depths[i]):Profile{});
    return result;
}
std::vector<Config> proposals(const Graph& g,const Profiles& p,const Histogram& hist,int uniform,Count cap) {
    Config cfg(p.size(),0);
    std::vector<Config> result{cfg};
    Count previous=0;
    for (;;) {
        double best=0;
        Count best_bytes=0;
        size_t chosen=0; int depth=0;
        for (size_t i=0;i<p.size();++i) {
            int h=cfg[i];
            Count gain=0;
            for (int j=h+1;j<=max_radius;++j) {
                gain+=hist.scans[i][j];
                if (!gain || (uniform && j!=uniform)) continue;
                cfg[i]=j;
                Count bytes=HotIndex::estimate(p,cfg,g.n);
                cfg[i]=h;
                if (bytes>cap) continue;
                double score=double(gain)/std::max<Count>(1,bytes>previous?bytes-previous:0);
                if (score>best || (score==best && bytes<best_bytes)) {
                    best=score; best_bytes=bytes; chosen=i; depth=j;
                }
            }
        }
        if (!best) break;
        cfg[chosen]=depth; previous=best_bytes;
        if (result.size()==1) result.push_back(cfg);
    }
    if (result.back()!=cfg) result.push_back(cfg);
    return result;
}

void fit(const Graph& g,Search& search,const fs::path& work,const fs::path& dest,
         const std::string& method,Count cap) {
    auto train=load_queries(work/"train.tsv",g.n,-1), val=load_queries(work/"validation.tsv",g.n,-1);
    auto start=Clock::now();
    auto roots=choose_roots(g,search,train);
    if (method=="profile") {
        auto degree=landmarks(g); std::sort(degree.begin(),degree.end());
        std::ofstream out(dest/"hotspots.tsv");
        out<<"split\tpool\troot\tdirection\tremaining\texpansions\tdistinct_sources\tscanned_edges\ttotal_graph_scans\n";
        for (auto pool:{&roots,&degree}) for (auto split:{&train,&val}) {
            auto hist=histogram(search,*split,*pool);
            for (size_t i=0;i<hist.scans.size();++i) for(int r=1;r<=max_radius;++r)
                out<<(split==&train?"train":"validation")<<'\t'<<(pool==&roots?"trace":"degree")<<'\t'
                   <<(*pool)[i/2]<<'\t'<<(i%2?"out":"in")<<'\t'<<r<<'\t'<<hist.visits[i][r]<<'\t'
                   <<hist.sources[i][r].size()<<'\t'<<hist.scans[i][r]<<'\t'<<hist.total<<'\n';
        }
        return;
    }
    auto hist=histogram(search,train,roots);
    auto p=profiles(g,roots,Config(2*roots.size(),max_radius));
    std::vector<Config> candidates;
    int first=method=="uniform"?1:0,last=first?max_radius:0;
    for (int h=first;h<=last;++h) for(auto& cfg:proposals(g,p,hist,h,cap))
        if (std::find(candidates.begin(),candidates.end(),cfg)==candidates.end()) candidates.push_back(cfg);
    Config chosen;
    double best=std::numeric_limits<double>::infinity();
    Count size=0;
    std::vector<std::tuple<size_t,double,double,Count>> scores;
    for(size_t i=0;i<candidates.size();++i) {
        auto tick=Clock::now();
        HotIndex index(p,candidates[i],roots,g.n);
        double encode=seconds(tick);
        auto t=khop_bench::measure(val.size(),[&](size_t n){return index.query(search,val[n]).yes;});
        for(size_t n=0;n<val.size();++n) check(val[n],{bool(t.answers[n]),'F',0});
        double score=encode+1e-3*double(t.median_ns)/val.size();
        scores.emplace_back(i,encode,score,index.bytes());
        if (score<best || (score==best && index.bytes()<size)) {
            best=score; chosen=candidates[i]; size=index.bytes();
        }
    }
    HotIndex final(p,chosen,roots,g.n);
    auto build=seconds(start);
    std::ofstream stats(dest/"fit.tsv");
    stats<<"build_s\tindex_bytes\tcandidates\n"<<std::setprecision(12)<<build<<'\t'<<final.bytes()<<'\t'<<scores.size()<<'\n';
    std::ofstream cfg(dest/"radii.tsv");
    cfg<<"root\tin\tout\n";
    for(size_t i=0;i<roots.size();++i) cfg<<roots[i]<<'\t'<<chosen[2*i]<<'\t'<<chosen[2*i+1]<<'\n';
    std::ofstream detail(dest/"validation.tsv");
    detail<<"candidate\tencode_s\tvalidation_cost_s\tbytes\tradii\n";
    for(auto [i,enc,cost,bytes]:scores) {
        detail<<i<<'\t'<<enc<<'\t'<<cost<<'\t'<<bytes<<'\t';
        for (int h:candidates[i]) detail<<h<<' ';
        detail<<'\n';
    }
}
template<class Fn>
void evaluate(const std::vector<Query>& qs,const fs::path& dest,Fn fn,Count bytes,double setup) {
    auto batch=khop_bench::measure(qs.size(),[&](size_t i){return fn(qs[i]).yes;});
    std::ofstream answers(dest/"answers.tsv");
    answers<<"yes\n";
    Count scans=0,certified=0;
    for(size_t i=0;i<qs.size();++i) {
        auto a=fn(qs[i]);
        check(qs[i],a);
        if (a.yes!=bool(batch.answers[i])) throw std::runtime_error("timed answer differs");
        answers<<int(a.yes)<<'\n';
        scans+=a.scans; certified+=(a.route=='U');
    }
    std::ofstream out(dest/"query.tsv");
    out<<"queries\tbatch_ns\tfirst_ns\trepeats\tindex_bytes\tscans\tcertified_true\tsetup_s\n"
       <<qs.size()<<'\t'<<batch.median_ns<<'\t'<<batch.first_ns<<'\t'<<batch.repeats<<'\t'<<bytes<<'\t'
       <<scans<<'\t'<<certified<<'\t'<<std::setprecision(12)<<setup<<'\n';
}
int main(int argc,char** argv) {
    if (argc!=9) throw std::runtime_error("hotspot phase method nodes edges workloads output config byte-cap");
    std::string phase=argv[1],method=argv[2];
    Graph g=Graph::load(std::stoul(argv[3]),argv[4]);
    Search search(g);
    fs::path work=argv[5],dest=argv[6];
    fs::create_directories(dest);
    if (phase=="fit") {
        if (method!="profile" && method!="uniform" && method!="adaptive") throw std::runtime_error("unknown fit");
        fit(g,search,work,dest,method,std::stoull(argv[8]));
        return 0;
    }
    if (phase!="eval") throw std::runtime_error("unknown phase");
    auto qs=load_queries(work/"benchmark.tsv",g.n,-1);
    auto start=Clock::now();
    if (method=="bibfs") {
        evaluate(qs,dest,[&](const Query& q){return search.run(q);},0,0);
    } else if (method=="tree") {
        CoverTree tree(g);
        double setup=seconds(start);
        Count bytes=sizeof(int)*tree.id.capacity()+sizeof(Node)*(tree.pre.capacity()+tree.post.capacity()+tree.depth.capacity());
        evaluate(qs,dest,[&](const Query& q){
            return tree.witness(g,q)?Answer{true,'U',0}:search.run(q);
        },bytes,setup);
    } else if (method=="uniform" || method=="adaptive" || method=="entry") {
        std::ifstream in(argv[7]); std::string header; std::getline(in,header);
        if (header!="root\tin\tout") throw std::runtime_error("invalid frozen radii");
        std::vector<Node> roots; Config cfg; Node v; int a,b;
        while (in>>v>>a>>b) {
            if(v>=g.n || (!roots.empty() && roots.back()>=v) || std::min(a,b)<0 || std::max(a,b)>max_radius)
                throw std::runtime_error("invalid radius row");
            roots.push_back(v); cfg.push_back(a);cfg.push_back(b);
        }
        if(!in.eof()) throw std::runtime_error("invalid radius file");
        auto p=profiles(g,roots,cfg);
        if(method=="entry") {
            Index idx(p,roots,cfg);
            evaluate(qs,dest,[&](const Query& q){return idx.query(g,search,q);},idx.bytes(),seconds(start));
        } else {
            HotIndex idx(p,cfg,roots,g.n);
            evaluate(qs,dest,[&](const Query& q){return idx.query(search,q);},idx.bytes(),seconds(start));
        }
    } else throw std::runtime_error("unknown method");
}
