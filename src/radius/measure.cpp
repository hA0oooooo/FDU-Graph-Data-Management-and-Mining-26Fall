#include "index.hpp"
#include "query_io.hpp"
#include "../benchmark_metrics.hpp"
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
std::vector<double> validation_scores(const Graph& g,Search& search,const std::vector<Query>& val,
                                      const std::vector<Index>& candidates) {
    std::vector<std::vector<double>> samples(candidates.size());
    for (size_t rep=0;rep<=6;++rep) for (size_t pos=0;pos<candidates.size();++pos) {
        size_t i=(rep+pos)%candidates.size();
        auto r=batch(val,[&](auto& q){return candidates[i].query(g,search,q);});
        if (rep) samples[i].push_back(r.avg);
    }
    std::vector<double> scores;
    for (const auto& sample:samples) scores.push_back(median(sample));
    return scores;
}
struct Method {
    std::string name;
    Config cfg;
    Index index;
    double build_ms;
};
int main(int argc,char** argv) {
    if (argc<5 || argc>9) throw std::runtime_error("measure N graph.edges workload_dir output_dir [fixed_k [test-file [label-cap-multiple [active-uniform]]]]");
    const int fixed_k=argc>=6?std::stoi(argv[5]):-1;
    const std::string test_file=argc>=7?argv[6]:"test.tsv";
    const Count budget_multiple=argc>=8?std::stoull(argv[7]):4;
    const bool active_uniform=argc==9 && std::stoi(argv[8])!=0;
    Graph g=Graph::load(std::stoul(argv[1]),argv[2]);
    Path data=argv[3], dest=argv[4];
    std::filesystem::create_directories(dest);
    auto train=load_queries(data/"train.tsv",g.n,fixed_k), val=load_queries(data/"validation.tsv",g.n,fixed_k);
    Search search(g);
    auto start=Clock::now();
    auto roots=landmarks(g);
    double root_ms=ms(start);
    Count cap=budget_multiple*g.n;
    if (cap<2*roots.size()) throw std::runtime_error("label cap cannot hold all implicit roots");
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
        auto scores=validation_scores(g,search,val,candidates);
        chosen=std::min_element(scores.begin(),scores.end())-scores.begin();
        for (size_t i=0;i<candidates.size();++i)
            valout<<i<<'\t'<<labels(p,Config(p.size(),i))<<'\t'<<scores[i]<<'\n';
    }
    double tune_ms=ms(start);
    Config active_cfg(p.size(),0);
    double active_tune_ms=0;
    if (active_uniform) {
        start=Clock::now();
        std::vector<Config> configs{Config(p.size(),0)};
        for (int h=1;h<=max_radius;++h)
            configs.push_back(allocate(p,cap,train,weights,h));
        std::vector<Index> candidates;
        for (const auto& cfg:configs) candidates.emplace_back(p,roots,cfg);
        auto scores=validation_scores(g,search,val,candidates);
        size_t chosen=std::min_element(scores.begin(),scores.end())-scores.begin();
        active_cfg=configs[chosen];
        std::ofstream active_val(dest/"validation-active.tsv");
        active_val<<"h\tlabels\tmedian_mean_us\n";
        for (size_t i=0;i<configs.size();++i)
            active_val<<i<<'\t'<<labels(p,configs[i])<<'\t'<<scores[i]<<'\n';
        active_tune_ms=ms(start);
    }
    std::vector<Method> methods;
    auto add=[&](std::string name,Config cfg) {
        auto tick=Clock::now();
        Index index(g,roots,cfg);
        auto duration=ms(tick);
        methods.push_back({name,cfg,std::move(index),duration});
    };
    add("uniform",Config(p.size(),chosen)); add("structural",structure);
    if (active_uniform) add("uniform-active",active_cfg);
    add("workload",learned);
    std::ofstream construction(dest/"build.tsv");
    construction<<"method\tcap\tlabels\ttable_bytes\troot_ms\tprofile_ms\tprofile_scans\ttraining_ms\ttraining_scans\tchoose_ms\tbuild_ms\tbuild_scans\tradii\n";
    for (auto& m:methods) {
        Count scans=0;
        for (size_t i=0;i<p.size();++i) for (int h=1;h<=m.cfg[i];++h) scans+=p[i].scans[h];
        bool learned_mode=m.name=="workload" || m.name=="uniform-active";
        construction<<m.name<<'\t'<<cap<<'\t'<<labels(p,m.cfg)<<'\t'<<m.index.bytes()<<'\t'<<root_ms<<'\t'
                    <<profile_ms<<'\t'<<probes<<'\t'<<(learned_mode?training_ms:0)<<'\t'<<(learned_mode?train_scans:0)
                    <<'\t'<<(m.name=="workload"?allocate_ms:m.name=="uniform-active"?active_tune_ms:m.name=="uniform"?tune_ms:structure_ms)
                    <<'\t'<<m.build_ms<<'\t'<<scans<<'\t';
        for (size_t i=0;i<m.cfg.size();++i) construction<<(i?",":"")<<m.cfg[i];
        construction<<'\n';
    }
    p.clear(); p.shrink_to_fit();
    // The test split is first opened after every configuration has been chosen.
    auto test=load_queries(data/test_file,g.n,fixed_k);
    uint64_t shared_ready=khop_bench::rss_kib();
    std::ofstream comparison(dest/"comparison.tsv");
    comparison<<"method\tqueries\tmismatches\tbatch_ns\tmedian_batch_ns\tquery_repeats\tshared_ready_rss_kib\n";
    for (auto& method:methods) {
        auto timing=khop_bench::measure(test.size(),[&](size_t i){
            return method.index.query(g,search,test[i]).yes;
        });
        Count errors=0;
        for(size_t i=0;i<test.size();++i)
            errors+=bool(timing.answers[i])!=(test[i].d>=0 && test[i].d<=test[i].k);
        Path folder=dest/"methods"/method.name;
        std::filesystem::create_directories(folder);
        std::ofstream stream(folder/"answers.tsv");
        stream<<"answer\n";
        for(auto answer:timing.answers)stream<<int(answer)<<'\n';
        comparison<<method.name<<'\t'<<test.size()<<'\t'<<errors<<'\t'<<timing.first_ns
                  <<'\t'<<timing.median_ns<<'\t'<<timing.repeats<<'\t'<<shared_ready<<'\n';
        if(errors)throw std::runtime_error("comparison batch mismatches");
    }
    std::ofstream repeats(dest/"repeats.tsv");
    repeats<<"method\trepeat\tn\tmean_us\tp95_us\tscans\tupper\tlower\ttrivial\tfallback\n";
    auto emit=[&](const std::string& m,int rep,const Run& r) {
        repeats<<std::setprecision(10)<<m<<'\t'<<rep<<'\t'<<test.size()<<'\t'<<r.avg<<'\t'<<r.p95<<'\t'
               <<r.scans<<'\t'<<r.upper<<'\t'<<r.lower<<'\t'<<r.trivial<<'\t'<<r.fallback<<'\n';
    };
    emit("bfs",1,batch(test,[&](auto& q){return search.run(q,false);}));
    const size_t count=methods.size()+1;
    for (int rep=0;rep<=12;++rep) for (size_t pos=0;pos<count;++pos) {
        size_t i=(pos+rep)%count;
        bool online=i==methods.size();
        Run r=batch(test,[&](auto& q){return online?search.run(q):methods[i].index.query(g,search,q);});
        if (rep) emit(online?"bibfs":methods[i].name,rep,r);
    }
}
