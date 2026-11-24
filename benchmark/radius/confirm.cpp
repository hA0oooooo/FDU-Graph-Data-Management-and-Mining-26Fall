// Read frozen configurations before opening any new held-out query group.
#include "../../src/radius/index.hpp"
#include <chrono>
#include <filesystem>
#include <iostream>
#include <sstream>

using namespace khop;
using Clock=std::chrono::steady_clock;
int main(int argc,char** argv) {
    if(argc!=5 && argc!=6)throw std::runtime_error("confirm N graph.edges saved_build.tsv holdout_dir [balanced]");
    bool balance=argc==6 && std::string(argv[5])=="balanced";
    // In four measured rounds each method occupies each position once and
    // every ordered pair of distinct methods occurs once as neighbors.
    const int orders[4][4]={{0,1,3,2},{1,2,0,3},{2,3,1,0},{3,0,2,1}};
    auto g=Graph::load(std::stoul(argv[1]),argv[2]);
    auto roots=landmarks(g);std::ifstream spec(argv[3]);std::string line;
    std::getline(spec,line);
    std::vector<std::string> names;std::vector<Index> indices;
    while(std::getline(spec,line)) {
        auto pos=line.rfind('\t');
        if(pos==std::string::npos)throw std::runtime_error("invalid build table");
        auto radii=line.substr(pos+1);std::replace(radii.begin(),radii.end(),',',' ');
        std::istringstream is(radii);int depth;Config h;
        while(is>>depth)h.push_back(depth);
        if(h.size()!=roots.size()*2)throw std::runtime_error("invalid radii");
        indices.emplace_back(g,roots,h);names.push_back(line.substr(0,line.find('\t')));
    }
    if(names!=std::vector<std::string>{"uniform","structural","workload"})throw std::runtime_error("missing policies");
    names.push_back("bibfs");Search search(g);
    std::cout<<"split\tmethod\trepeat\tn\tmean_us\tscans\tupper\tlower\ttrivial\tfallback\n";
    for(std::string split:{"holdout-1","holdout-2","holdout-3"}) {
        std::ifstream f(std::filesystem::path(argv[4])/(split+".tsv"));
        std::getline(f,line);std::vector<Query> qs;Query q;
        while(f>>q.s>>q.t>>q.k>>q.d)qs.push_back(q);
        if(qs.empty())throw std::runtime_error("missing holdout");
        for(int rep=0;rep<=12;++rep)for(int pos=0;pos<4;++pos) {
            int i=balance?orders[rep%4][pos]:(pos+rep)%4;
            auto evaluate=[&](const Query& item) {
                return i==3?search.run(item):indices[i].query(g,search,item);
            };
            if(balance) {
                for(auto item:qs) if(evaluate(item).yes!=(item.d>=0 && item.d<=item.k))
                    throw std::runtime_error("warmup mismatch");
            }
            double us=0;Count edges=0,up=0,lo=0,triv=0,fall=0;
            for(auto item:qs) {
                auto tick=Clock::now();
                Answer a=evaluate(item);
                us+=std::chrono::duration<double,std::micro>(Clock::now()-tick).count();
                if(a.yes!=(item.d>=0 && item.d<=item.k))throw std::runtime_error("holdout mismatch");
                edges+=a.scans;up+=a.route=='U';lo+=a.route=='L';triv+=a.route=='T';fall+=a.route=='F';
            }
            if(rep)std::cout<<split<<'\t'<<names[i]<<'\t'<<rep<<'\t'<<qs.size()<<'\t'<<us/qs.size()
                            <<'\t'<<edges<<'\t'<<up<<'\t'<<lo<<'\t'<<triv<<'\t'<<fall<<'\n';
        }
    }
}
