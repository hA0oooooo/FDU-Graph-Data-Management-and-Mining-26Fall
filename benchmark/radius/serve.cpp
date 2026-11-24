// Time one native batch after final index construction; verify outside the timer.
#include "../../src/radius/index.hpp"
#include <chrono>
#include <iostream>
#include <sstream>
using namespace khop;
using Clock=std::chrono::steady_clock;
int main(int argc,char** argv) {
    if(argc!=5)throw std::runtime_error("serve N graph.edges test.tsv build.tsv");
    auto g=Graph::load(std::stoul(argv[1]),argv[2]);
    auto roots=landmarks(g);
    std::vector<Query> qs;Query q;std::string line;
    std::ifstream f(argv[3]);std::getline(f,line);
    while(f>>q.s>>q.t>>q.k>>q.d)qs.push_back(q);
    if(qs.empty())throw std::runtime_error("empty workload");
    std::vector<char> result(qs.size());
    std::cout<<"method\tn\tbatch_ms\n";
    auto batch=[&](const std::string& name,auto query) {
        auto start=Clock::now();
        for(size_t i=0;i<qs.size();++i) result[i]=query(qs[i]).yes;
        auto elapsed=std::chrono::duration<double,std::milli>(Clock::now()-start).count();
        for(size_t i=0;i<qs.size();++i) if(bool(result[i])!=(qs[i].d>=0 && qs[i].d<=qs[i].k))
            throw std::runtime_error("batch mismatch");
        std::cout<<name<<'\t'<<qs.size()<<'\t'<<elapsed<<'\n';
    };
    for(bool both:{false,true}) {
        Search search(g);batch(both?"bibfs":"bfs",[&](auto& query){return search.run(query,both);});
    }
    std::ifstream spec(argv[4]);std::getline(spec,line);int count=0;
    while(std::getline(spec,line)) {
        auto pos=line.rfind('\t');if(pos==std::string::npos)throw std::runtime_error("invalid build table");
        auto r=line.substr(pos+1);std::replace(r.begin(),r.end(),',',' ');
        std::istringstream stream(r);Config cfg;int h;while(stream>>h)cfg.push_back(h);
        if(cfg.size()!=2*roots.size())throw std::runtime_error("invalid radii");
        Search search(g);Index index(g,roots,cfg);
        batch(line.substr(0,line.find('\t')),[&](auto& query){return index.query(g,search,query);});++count;
    }
    if(count!=3)throw std::runtime_error("missing configuration");
}
