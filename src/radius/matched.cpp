#include "index.hpp"
#include <chrono>
#include <iostream>
#include <sstream>

using namespace khop;
using Clock=std::chrono::steady_clock;

int main(int argc,char** argv) {
    if (argc!=5) throw std::runtime_error("matched N graph.edges test.tsv build.tsv");
    auto g=Graph::load(std::stoul(argv[1]),argv[2]);
    std::ifstream builds(argv[4]); std::string line;
    Config learned; Count cap=0;
    while(std::getline(builds,line)) {
        std::istringstream row(line);
        std::string word;
        if(!(row>>word) || word!="workload")continue;
        Count full_budget;
        row>>full_budget>>cap;
        while(row>>word) if(word.find(',')!=std::string::npos) {
            std::replace(word.begin(),word.end(),',',' ');
            std::istringstream radii(word);int h;
            while(radii>>h)learned.push_back(h);
        }
    }
    auto roots=landmarks(g); Profiles p;
    if(learned.size()!=2*roots.size())throw std::runtime_error("invalid learned radii");
    for(auto r:roots)for(int dir:{0,1})p.push_back(explore(g.side[dir],r,max_radius));
    if(labels(p,learned)!=cap)throw std::runtime_error("workload entry count mismatch");
    auto other=structural(p,cap);
    std::array<Index,2> indices={Index(p,roots,learned),Index(p,roots,other)};
    Count entries[]={cap,labels(p,other)};
    p.clear();p.shrink_to_fit();
    std::ifstream file(argv[3]);std::getline(file,line);
    std::vector<Query> qs;Query q;
    while(file>>q.s>>q.t>>q.k>>q.d)qs.push_back(q);
    if(qs.empty())throw std::runtime_error("empty test file");
    Search search(g);
    std::cout<<"method\trepeat\tentries\tbytes\tscans\thits\tmean_us\n";
    for(int rep=0;rep<=12;++rep)for(int j=0;j<2;++j) {
        int m=(j+rep)%2;
        Count scans=0,hits=0;double us=0;
        for(auto& item:qs) {
            auto tick=Clock::now();auto a=indices[m].query(g,search,item);
            us+=std::chrono::duration<double,std::micro>(Clock::now()-tick).count();
            if(a.yes!=(item.d>=0 && item.d<=item.k))throw std::runtime_error("wrong answer");
            scans+=a.scans;hits+=(a.route=='U'||a.route=='L');
        }
        if(rep)std::cout<<(m?"structural-matched":"workload")<<'\t'<<rep<<'\t'<<entries[m]<<'\t'<<indices[m].bytes()
                         <<'\t'<<scans<<'\t'<<hits<<'\t'<<us/qs.size()<<'\n';
    }
}
