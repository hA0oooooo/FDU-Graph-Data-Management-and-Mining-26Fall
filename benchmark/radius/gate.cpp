#include "../../src/radius/index.hpp"
#include <chrono>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>

using namespace khop;
using Clock=std::chrono::steady_clock;
using Path=std::filesystem::path;

double elapsed_ms(Clock::time_point start) {
    return std::chrono::duration<double,std::milli>(Clock::now()-start).count();
}
std::vector<Query> read_queries(const Path& path,Node n) {
    std::ifstream f(path);
    std::string header;
    std::getline(f,header);
    if(header!="s\tt\tk\td") throw std::runtime_error("bad workload header");
    std::vector<Query> out;Query q;
    while(f>>q.s>>q.t>>q.k>>q.d) {
        if(q.s>=n || q.t>=n || q.d< -1 || q.k<0) throw std::runtime_error("bad workload row");
        out.push_back(q);
    }
    if(!f.eof() || out.empty()) throw std::runtime_error("empty or incomplete workload");
    return out;
}
std::array<Config,2> configs(const Path& path,size_t roots) {
    std::array<Config,2> cs;
    std::ifstream in(path);std::string line;std::getline(in,line);
    while(std::getline(in,line)) {
        auto name=line.substr(0,line.find('\t'));
        if(name!="uniform" && name!="workload")continue;
        Config& c=cs[name=="uniform"?0:1];
        std::string raw=line.substr(line.rfind('\t')+1);
        std::replace(raw.begin(),raw.end(),',',' ');
        std::istringstream vals(raw);int x;
        while(vals>>x) {
            if(x<0 || x>max_radius)throw std::runtime_error("bad radius");
            c.push_back(x);
        }
    }
    for(auto& c:cs) if(c.size()!=2*roots)throw std::runtime_error("missing/duplicate configuration");
    return cs;
}

struct Metrics { double us; Count scans=0,upper=0,lower=0; };
template<class F> Metrics measure(const std::vector<Query>& qs,std::vector<Answer>& output,F&& method) {
    auto start=Clock::now();
    for(size_t i=0;i<qs.size();++i)output[i]=method(qs[i]);
    double us=elapsed_ms(start)*1000/qs.size();
    Metrics m{us};
    for(size_t i=0;i<qs.size();++i) {
        auto& a=output[i];auto& q=qs[i];
        if(a.yes!=(q.d>=0 && q.d<=q.k))throw std::runtime_error("gate answer disagrees with exact distance");
        m.scans+=a.scans;m.upper+=a.route=='U';m.lower+=a.route=='L';
    }
    return m;
}

struct Decision { unsigned wins=0; double margin=0; bool enabled=false; };
struct Policy {
    const char* name;
    Config h;
    Index index;
    double rebuild_ms;
    std::array<bool,7> gate{};
    bool enabled(int k) const {return k>=0 && k<int(gate.size()) && gate[k];}
};

int main(int argc,char** argv) {
    if(argc!=7)throw std::invalid_argument("gate N graph.edges build.tsv validation.tsv new_holdouts output");
    auto g=Graph::load(std::stoul(argv[1]),argv[2]);
    auto roots=landmarks(g);
    auto cs=configs(argv[3],roots.size());
    Path dest=argv[6];
    std::vector<Policy> ps;
    for(int i=0;i<2;++i) {
        auto start=Clock::now();
        Index idx(g,roots,cs[i]);
        double rebuild=elapsed_ms(start);
        ps.push_back({i==0?"uniform":"workload",cs[i],std::move(idx),rebuild});
    }
    auto valid=read_queries(argv[4],g.n);
    std::ofstream decisions(dest/"gate-decisions.tsv"), rounds(dest/"gate-validation.tsv"), costs(dest/"gate-cost.tsv");
    decisions<<"policy\tk\tn\twins\tmedian_fraction_saved\tenabled\treason\n";
    rounds<<"policy\tk\trepeat\tindex_us\tbibfs_us\n";
    costs<<"policy\trebuild_ms\tvalidation_gate_ms\n";
    decisions<<std::setprecision(12);rounds<<std::setprecision(12);costs<<std::setprecision(12);
    Search search(g);
    for(auto& p:ps) {
        auto tick=Clock::now();
        const bool zero=std::all_of(p.h.begin(),p.h.end(),[](int x){return x==0;});
        // Keep the measured choice cost free of output-file traffic.
        std::ostringstream log_dec,log_reps;
        log_dec<<std::setprecision(12);log_reps<<std::setprecision(12);
        for(int k:{2,4,6}) {
            std::vector<Query> group;
            for(auto q:valid)if(q.k==k)group.push_back(q);
            Decision result;
            const char* reason=zero?"zero-radius":group.empty()?"no-validation-sample":"validation";
            if(!zero && !group.empty()) {
                std::array<double,12> gains;
                std::vector<Answer> ans(group.size());
                for(int rep=0;rep<12;++rep) {
                    std::array<double,2> t;
                    for(int pos=0;pos<2;++pos) {
                        int m=(rep+pos)%2;
                        auto act=[&](const Query& q){return m?p.index.query(g,search,q):search.run(q);};
                        measure(group,ans,act); // Own-method warmup
                        t[m]=measure(group,ans,act).us;
                    }
                    result.wins+=(t[1]<t[0]);
                    gains[rep]=(t[0]-t[1])/t[0];
                    log_reps<<p.name<<'\t'<<k<<'\t'<<rep+1<<'\t'<<t[1]<<'\t'<<t[0]<<'\n';
                }
                std::sort(gains.begin(),gains.end());
                result.margin=(gains[5]+gains[6])/2;
                result.enabled=result.wins>=9 && result.margin>=0.05;
            }
            p.gate[k]=result.enabled;
            log_dec<<p.name<<'\t'<<k<<'\t'<<group.size()<<'\t'<<result.wins<<'\t'<<result.margin<<'\t'
                   <<result.enabled<<'\t'<<reason<<'\n';
        }
        double choose_ms=elapsed_ms(tick);
        costs<<p.name<<'\t'<<p.rebuild_ms<<'\t'<<choose_ms<<'\n';
        decisions<<log_dec.str();rounds<<log_reps.str();
    }
    decisions.close();rounds.close();costs.close();
    // The holdouts are first opened after both decision tables are final.
    std::ofstream held(dest/"gate-confirm.tsv");
    held<<std::setprecision(12)<<"split\tmethod\trepeat\tn\tmean_us\tscans\tupper\tlower\terrors\n";
    const char* names[]={"gated-workload","gated-uniform","workload","bibfs"};
    const int order[4][4]={{0,1,3,2},{1,2,0,3},{2,3,1,0},{3,0,2,1}};
    for(int group=1;group<=3;++group) {
        std::string split="holdout-"+std::to_string(group);
        auto qs=read_queries(Path(argv[5])/(split+".tsv"),g.n);
        std::vector<Answer> out(qs.size());
        for(int rep=0;rep<12;++rep) for(auto m:order[rep%4]) {
            auto act=[&](const Query& q) {
                if(m==3)return search.run(q);
                if(m==2)return ps[1].index.query(g,search,q);
                auto& p=ps[1-m];
                return p.enabled(q.k)?p.index.query(g,search,q):search.run(q);
            };
            measure(qs,out,act);
            auto r=measure(qs,out,act);
            held<<split<<'\t'<<names[m]<<'\t'<<rep+1<<'\t'<<qs.size()<<'\t'<<r.us<<'\t'
                <<r.scans<<'\t'<<r.upper<<'\t'<<r.lower<<"\t0\n";
        }
    }
    if(!held || !decisions || !costs || !rounds)throw std::runtime_error("gate output failed");
}
