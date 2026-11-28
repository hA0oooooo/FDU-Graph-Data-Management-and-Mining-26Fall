#include "hotspot_training.hpp"
#include "filters.hpp"
#include "query_io.hpp"
#include "../benchmark_metrics.hpp"
#include <chrono>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <map>

using namespace khop;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;

double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now()-start).count();
}
void read_config(const fs::path& path,Node n,std::vector<Node>& roots,Config& cfg) {
    std::ifstream in(path); std::string header; std::getline(in,header);
    if (header!="root\tin\tout") throw std::runtime_error("invalid frozen radii");
    Node v; int a,b;
    while (in>>v>>a>>b) {
        if(v>=n || (!roots.empty() && roots.back()>=v) || std::min(a,b)<0 || std::max(a,b)>max_radius)
            throw std::runtime_error("invalid radius row");
        roots.push_back(v); cfg.push_back(a);cfg.push_back(b);
    }
    if(!in.eof()) throw std::runtime_error("invalid radius file");
}

// Exact representation of the allocated immutable table, for hashing outside the timed region.
void export_table(const HotIndex& index,const fs::path& path) {
    std::ofstream out(path,std::ios::binary);
    auto scalar=[&](uint64_t x){out.write(reinterpret_cast<const char*>(&x),sizeof(x));};
    scalar(index.tables.size());
    for (const auto& pair:index.tables) for (const Table* t:{&pair.first,&pair.second}) {
        scalar(t->root); scalar(t->h); scalar(t->dense);
        scalar(t->ids.size()); scalar(t->values.size());
        if (!t->ids.empty()) out.write(reinterpret_cast<const char*>(t->ids.data()),sizeof(Node)*t->ids.size());
        if (!t->values.empty()) out.write(reinterpret_cast<const char*>(t->values.data()),t->values.size());
    }
    if (!out) throw std::runtime_error("table export failed");
}
void fit(const Graph& g,Search& search,const fs::path& work,const fs::path& dest,
         const std::string& method,Count cap,int fixed_k,const std::string& pool_name,
         const std::string& policy="full",const fs::path& frozen={},bool study=false) {
    auto train=load_queries(work/"train.tsv",g.n,fixed_k);
    auto val=frozen.empty()?load_queries(work/"validation.tsv",g.n,fixed_k):std::vector<Query>{};
    auto start=Clock::now();
    auto roots=(method=="profile" || pool_name=="trace") ? choose_roots(g,search,train) : landmarks(g);
    std::sort(roots.begin(),roots.end());
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
    double training=seconds(start);
    Config chosen;
    if (!frozen.empty()) {
        std::vector<Node> fixed_roots;
        read_config(frozen,g.n,fixed_roots,chosen);
        if (fixed_roots!=roots) throw std::logic_error("fixed roots differ from training");
    }
    auto tick=Clock::now();
    int k=fixed_k>0?fixed_k:6;
    auto limits=probe_limits(hist,policy,k);
    auto p=profiles(g,roots,limits);
    double probe=seconds(tick);
    tick=Clock::now();
    auto candidates=candidates_for(g,p,hist,limits,method=="uniform",policy=="full"?max_radius:k-1,cap);
    double choose=seconds(tick);
    if (!frozen.empty() && std::find(candidates.begin(),candidates.end(),chosen)==candidates.end())
        throw std::logic_error("fixed configuration is not a candidate");
    tick=Clock::now();
    double best=std::numeric_limits<double>::infinity();
    Count size=0;
    std::vector<std::tuple<size_t,double,double,Count>> scores;
    for(size_t i=0;frozen.empty() && i<candidates.size();++i) {
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
    double validation=seconds(tick);
    tick=Clock::now();
    HotIndex final(p,chosen,roots,g.n);
    double encode=seconds(tick);
    double build=frozen.empty()?training+probe+choose+validation+encode:training+probe+encode;
    if (!study) build=seconds(start);
    if (study) {
        export_table(final,dest/"table.bin");
        std::ofstream detail(dest/"candidates.tsv");
        detail<<"candidate\tradii\n";
        for (size_t i=0;i<candidates.size();++i) {
            detail<<i<<'\t';
            for (int h:candidates[i]) detail<<h<<' ';
            detail<<'\n';
        }
        std::ofstream dirs(dest/"directions.tsv");
        dirs<<"root\tdirection\tlimit\tchosen_h\tscans\n";
        for (size_t i=0;i<limits.size();++i) {
            auto scans=std::accumulate(p[i].scans.begin(),p[i].scans.end(),Count(0));
            dirs<<roots[i/2]<<'\t'<<(i%2?"out":"in")<<'\t'<<limits[i]<<'\t'<<chosen[i]<<'\t'<<scans<<'\n';
        }
    }
    std::ofstream stats(dest/"fit.tsv");
    Count scanned=0;
    for (const auto& direction:p) scanned+=std::accumulate(direction.scans.begin(),direction.scans.end(),Count(0));
    stats<<"build_s\tindex_bytes\tcandidates\ttraining_s\tprobe_s\tchoose_s\tvalidation_s\tencode_s\tprobe_scans\n"
         <<std::setprecision(12)<<build<<'\t'<<final.bytes()<<'\t'<<candidates.size()<<'\t'<<training<<'\t'<<probe<<'\t'
         <<choose<<'\t'<<validation<<'\t'<<encode<<'\t'<<scanned<<'\n';
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
void evaluate(const std::vector<Query>& qs,const fs::path& dest,Fn fn,Count bytes,double setup,bool study=false,bool transfer=false) {
    auto batch=khop_bench::measure(qs.size(),[&](size_t i){return fn(qs[i]).yes;});
    std::ofstream answers(dest/"answers.tsv");
    answers<<"yes\n";
    Count scans=0,certified=0;
    struct Group {Count n=0,scans=0;};
    std::map<std::pair<int,std::string>,Group> groups;
    std::ofstream details;
    if(study) {
        details.open(dest/"details.tsv");
        details<<"yes\troute\tscans\n";
    }
    for(size_t i=0;i<qs.size();++i) {
        auto a=fn(qs[i]);
        check(qs[i],a);
        if (a.yes!=bool(batch.answers[i])) throw std::runtime_error("timed answer differs");
        answers<<int(a.yes)<<'\n';
        scans+=a.scans; certified+=(a.route=='U');
        if (study) {
            details<<a.yes<<'\t'<<a.route<<'\t'<<a.scans<<'\n';
            const auto& q=qs[i];
            auto& group=groups[{q.k,q.d<0?"unreachable":q.d>q.k?"beyond":"within"}];
            ++group.n; group.scans+=a.scans;
        }
    }
    if (study) {
        std::ofstream detail(dest/"groups.tsv");
        detail<<"k\tclass\tqueries\tscans\n";
        for (int k:{2,4,6}) for (std::string name:{"within","beyond","unreachable"}) {
            auto group=groups[{k,name}];
            detail<<k<<'\t'<<name<<'\t'<<group.n<<'\t'<<group.scans<<'\n';
        }
        if(transfer) {
            std::ofstream by_k(dest/"threshold.tsv");
            by_k<<"k\tqueries\tbatch_ns\n";
            for (int k:{2,4,6}) {
                std::vector<size_t> rows;
                for(size_t i=0;i<qs.size();++i) if(qs[i].k==k) rows.push_back(i);
                if(rows.empty()) {by_k<<k<<"\t0\tNA\n";continue;}
                auto t=khop_bench::measure(rows.size(),[&](size_t i){return fn(qs[rows[i]]).yes;});
                for(size_t i=0;i<rows.size();++i) check(qs[rows[i]],{bool(t.answers[i]),'F',0});
                by_k<<k<<'\t'<<rows.size()<<'\t'<<t.median_ns<<'\n';
            }
        }
    }
    std::ofstream out(dest/"query.tsv");
    out<<"queries\tbatch_ns\tfirst_ns\trepeats\tindex_bytes\tscans\tcertified_true\tsetup_s\n"
       <<qs.size()<<'\t'<<batch.median_ns<<'\t'<<batch.first_ns<<'\t'<<batch.repeats<<'\t'<<bytes<<'\t'
       <<scans<<'\t'<<certified<<'\t'<<std::setprecision(12)<<setup<<'\n';
}
int main(int argc,char** argv) {
    if (argc!=9 && argc!=11) throw std::runtime_error("hotspot phase method nodes edges workloads output config byte-cap [fixed-k pool]");
    const int fixed_k=argc==11?std::stoi(argv[9]):-1;
    const std::string pool=argc==11?argv[10]:"trace";
    if (pool!="degree" && pool!="trace") throw std::invalid_argument("unknown candidate pool");
    std::string phase=argv[1],method=argv[2];
    Graph g=Graph::load(std::stoul(argv[3]),argv[4]);
    Search search(g);
    fs::path work=argv[5],dest=argv[6];
    fs::create_directories(dest);
    if (phase=="study-fit" || phase=="study-build") {
        bool uniform=method=="uniform-global";
        if(!uniform && method.rfind("adaptive-",0)!=0) throw std::runtime_error("invalid study method");
        auto policy=uniform?std::string("global"):method.substr(9);
        fit(g,search,work,dest,uniform?"uniform":"adaptive",std::stoull(argv[8]),fixed_k,pool,
            policy,phase=="study-build"?fs::path(argv[7]):fs::path{},true);
        return 0;
    }
    if (phase=="fit") {
        if (method!="profile" && method!="uniform" && method!="adaptive") throw std::runtime_error("unknown fit");
        fit(g,search,work,dest,method,std::stoull(argv[8]),fixed_k,pool);
        return 0;
    }
    bool study=phase=="study-eval" || phase=="study-transfer";
    if (phase!="eval" && !study) throw std::runtime_error("unknown phase");
    auto qs=load_queries(study?work:work/"benchmark.tsv",g.n,fixed_k);
    auto start=Clock::now();
    if (method=="bibfs") {
        evaluate(qs,dest,[&](const Query& q){return search.run(q);},0,0,study,phase=="study-transfer");
    } else if (method=="tree") {
        CoverTree tree(g);
        double setup=seconds(start);
        Count bytes=sizeof(int)*tree.id.capacity()+sizeof(Node)*(tree.pre.capacity()+tree.post.capacity()+tree.depth.capacity());
        evaluate(qs,dest,[&](const Query& q){
            return tree.witness(g,q)?Answer{true,'U',0}:search.run(q);
        },bytes,setup);
    } else if (method=="uniform" || method=="adaptive" || method=="entry" || study) {
        std::vector<Node> roots; Config cfg;
        read_config(argv[7],g.n,roots,cfg);
        auto p=profiles(g,roots,cfg);
        if(method=="entry") {
            Index idx(p,roots,cfg);
            evaluate(qs,dest,[&](const Query& q){return idx.query(g,search,q);},idx.bytes(),seconds(start));
        } else {
            HotIndex idx(p,cfg,roots,g.n);
            double setup=seconds(start);
            if(study) export_table(idx,dest/"table.bin");
            evaluate(qs,dest,[&](const Query& q){return idx.query(search,q);},idx.bytes(),setup,study,phase=="study-transfer");
        }
    } else throw std::runtime_error("unknown method");
}
