#include "../../src/radius/index.hpp"
#include <chrono>
#include <filesystem>
#include <iomanip>
#include <iostream>

using namespace khop;
using Clock=std::chrono::steady_clock;
using Path=std::filesystem::path;
double ms(Clock::time_point start) {
    return std::chrono::duration<double,std::milli>(Clock::now()-start).count();
}
double median(std::vector<double> xs) {
    std::sort(xs.begin(),xs.end());
    return (xs[(xs.size()-1)/2]+xs[xs.size()/2])/2;
}
std::vector<Query> load_queries(const Path& path,Node n,int fixed_k) {
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
void check(const Query& q,Answer a) {
    if (a.yes!=(q.d>=0 && q.d<=q.k))
        throw std::runtime_error("wrong answer at "+std::to_string(q.s)+","+std::to_string(q.t)+","+std::to_string(q.k));
}
struct Run {
    double avg,p95;
    Count scans, upper,lower,trivial,fallback;
};
template<class F> Run batch(const std::vector<Query>& qs,F&& method) {
    std::vector<double> times;
    times.reserve(qs.size());
    Count scans=0,up=0,low=0,triv=0,back=0;
    double total=0;
    for (const auto& q:qs) {
        auto start=Clock::now();
        auto answer=method(q);
        auto elapsed=ms(start)*1000;
        check(q,answer);
        total+=elapsed; times.push_back(elapsed); scans+=answer.scans;
        up+=answer.route=='U'; low+=answer.route=='L'; triv+=answer.route=='T'; back+=answer.route=='F';
    }
    std::sort(times.begin(),times.end());
    return {total/qs.size(),times[(qs.size()*95+99)/100-1],scans,up,low,triv,back};
}
struct Method {
    std::string name;
    Config cfg;
    Index index;
    double build_ms;
};
int main(int argc,char** argv) {
    if (argc!=5 && argc!=6) throw std::runtime_error("measure N graph.edges workload_dir output_dir [fixed_k]");
    const int fixed_k=argc==6?std::stoi(argv[5]):-1;
    Graph g=Graph::load(std::stoul(argv[1]),argv[2]);
    Path data=argv[3], dest=argv[4];
    std::filesystem::create_directories(dest);
    auto train=load_queries(data/"train.tsv",g.n,fixed_k), val=load_queries(data/"validation.tsv",g.n,fixed_k);
    Search search(g);
    auto start=Clock::now();
    auto roots=landmarks(g);
    double root_ms=ms(start);
    Count cap=Count(4)*g.n;
    start=Clock::now();
    Profiles p;
    Count probes=0;
    for (auto u:roots) for (int side:{0,1}) {
        p.push_back(explore(g.side[side],u,max_radius));
        for (auto e:p.back().scans) probes+=e;
    }
    double profile_ms=ms(start);
    start=Clock::now();
    std::vector<unsigned> weights;
    Count train_scans=0;
    for (auto& q:train) {
        auto a=search.run(q); check(q,a);
        weights.push_back(std::min<Count>(a.scans,4096)); train_scans+=a.scans;
    }
    double training_ms=ms(start);
    start=Clock::now();
    auto learned=allocate(p,cap,train,weights);
    double allocate_ms=ms(start);
    start=Clock::now();
    auto structure=structural(p,cap);
    double structure_ms=ms(start);
    std::ofstream valout(dest/"validation.tsv");
    valout<<"h\tlabels\tmedian_mean_us\n";
    start=Clock::now();
    int chosen=0;
    {
        std::vector<Index> candidates;
        for (int h=0;h<=max_radius;++h) {
            Config cfg(p.size(),h);
            if (labels(p,cfg)>cap) break;
            candidates.emplace_back(p,roots,cfg);
        }
        std::vector<std::vector<double>> scores(candidates.size());
        for (size_t rep=0;rep<=6;++rep) for (size_t pos=0;pos<candidates.size();++pos) {
            size_t i=(rep+pos)%candidates.size();
            auto r=batch(val,[&](auto& q){return candidates[i].query(g,search,q);});
            if (rep) scores[i].push_back(r.avg);
        }
        double best=std::numeric_limits<double>::infinity();
        for (size_t i=0;i<candidates.size();++i) {
            auto v=median(scores[i]); valout<<i<<'\t'<<labels(p,Config(p.size(),i))<<'\t'<<v<<'\n';
            if (v<best) {best=v; chosen=i;}
        }
    }
    double tune_ms=ms(start);
    std::vector<Method> methods;
    auto add=[&](std::string name,Config cfg) {
        auto tick=Clock::now();
        Index index(g,roots,cfg);
        auto duration=ms(tick);
        methods.push_back({name,cfg,std::move(index),duration});
    };
    add("uniform",Config(p.size(),chosen)); add("structural",structure); add("workload",learned);
    std::ofstream construction(dest/"build.tsv");
    construction<<"method\tcap\tlabels\ttable_bytes\troot_ms\tprofile_ms\tprofile_scans\ttraining_ms\ttraining_scans\tchoose_ms\tbuild_ms\tbuild_scans\tradii\n";
    for (auto& m:methods) {
        Count scans=0;
        for (size_t i=0;i<p.size();++i) for (int h=1;h<=m.cfg[i];++h) scans+=p[i].scans[h];
        bool learned_mode=m.name=="workload";
        construction<<m.name<<'\t'<<cap<<'\t'<<labels(p,m.cfg)<<'\t'<<m.index.bytes()<<'\t'<<root_ms<<'\t'
                    <<profile_ms<<'\t'<<probes<<'\t'<<(learned_mode?training_ms:0)<<'\t'<<(learned_mode?train_scans:0)
                    <<'\t'<<(learned_mode?allocate_ms:m.name=="uniform"?tune_ms:structure_ms)
                    <<'\t'<<m.build_ms<<'\t'<<scans<<'\t';
        for (size_t i=0;i<m.cfg.size();++i) construction<<(i?",":"")<<m.cfg[i];
        construction<<'\n';
    }
    p.clear(); p.shrink_to_fit();
    // The test split is first opened after every configuration has been chosen.
    auto test=load_queries(data/"test.tsv",g.n,fixed_k);
    std::ofstream repeats(dest/"repeats.tsv");
    repeats<<"method\trepeat\tn\tmean_us\tp95_us\tscans\tupper\tlower\ttrivial\tfallback\n";
    auto emit=[&](const std::string& m,int rep,const Run& r) {
        repeats<<std::setprecision(10)<<m<<'\t'<<rep<<'\t'<<test.size()<<'\t'<<r.avg<<'\t'<<r.p95<<'\t'
               <<r.scans<<'\t'<<r.upper<<'\t'<<r.lower<<'\t'<<r.trivial<<'\t'<<r.fallback<<'\n';
    };
    emit("bfs",1,batch(test,[&](auto& q){return search.run(q,false);}));
    for (int rep=0;rep<=12;++rep) for (int pos=0;pos<4;++pos) {
        int i=(pos+rep)%4;
        Run r=batch(test,[&](auto& q){return i==3?search.run(q):methods[i].index.query(g,search,q);});
        if (rep) emit(i==3?"bibfs":methods[i].name,rep,r);
    }
}
