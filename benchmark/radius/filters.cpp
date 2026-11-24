#include "../../src/radius/filters.hpp"
#include <chrono>
#include <iomanip>
#include <iostream>
using namespace khop;
using Clock=std::chrono::steady_clock;

template<class Filter> void measure(const char* name,const Graph& g,const std::vector<Query>& qs) {
    auto before=Clock::now();
    Filter filter(g);
    double build=std::chrono::duration<double,std::milli>(Clock::now()-before).count();
    Search search(g);
    for(int rep=0;rep<=5;++rep) {
        double us=0;Count scans=0,hits=0;
        for(auto q:qs) {
            auto start=Clock::now(); bool yes;
            if(q.s==q.t || !q.k || !g.side[1].degree(q.s) || !g.side[0].degree(q.t)) yes=q.s==q.t;
            else if(char wit=filter.witness(g,q)) {yes=wit=='U';++hits;}
            else {auto a=search.run(q);yes=a.yes;scans+=a.scans;}
            us+=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
            if(yes!=(q.d>=0 && q.d<=q.k)) throw std::runtime_error("filter mismatch");
        }
        if(rep)std::cout<<name<<'\t'<<rep<<'\t'<<qs.size()<<'\t'<<build<<'\t'<<hits<<'\t'<<scans<<'\t'<<us/qs.size()<<'\n';
    }
}
int main(int argc,char** argv) {
    if(argc!=4) return 2;
    auto g=Graph::load(std::stoul(argv[1]),argv[2]);std::ifstream f(argv[3]);
    std::string header;std::getline(f,header);std::vector<Query> qs;Query q;
    while(f>>q.s>>q.t>>q.k>>q.d) qs.push_back(q);
    if(qs.empty())return 2;
    std::cout<<"filter\trepeat\tqueries\tbuild_ms\thits\tscans\tmean_us\n";
    measure<Topology>("scc-two-orders",g,qs);measure<CoverTree>("cover-tree",g,qs);
}
