#include "../../src/radius/index.hpp"
#include <iostream>
#include <map>
#include <sstream>
using namespace khop;

struct Counts {Count n=0, scans=0,upper=0,lower=0,trivial=0,fallback=0,saved=0;};
int main(int argc,char** argv) {
    if(argc!=5)throw std::runtime_error("routes N graph.edges test.tsv build.tsv");
    Graph g=Graph::load(std::stoul(argv[1]),argv[2]);
    auto roots=landmarks(g);std::ifstream specs(argv[4]);std::string line;std::getline(specs,line);
    std::vector<std::string> names;std::vector<Index> indices;
    while(std::getline(specs,line)) {
        std::istringstream row(line);
        std::string name,last;
        if(!(row>>name))continue;
        while(row>>last) {if(last.find(',')!=std::string::npos)break;}
        std::replace(last.begin(),last.end(),',',' ');
        std::istringstream radii(last);Config cfg;int h;
        while(radii>>h)cfg.push_back(h);
        if(cfg.size()!=roots.size()*2)throw std::runtime_error("invalid radius record");
        names.push_back(name);indices.emplace_back(g,roots,cfg);
    }
    if(indices.size()!=3)throw std::runtime_error("expected three frozen configurations");
    std::ifstream file(argv[3]);std::getline(file,line);Query q;
    Search search(g);std::map<std::tuple<std::string,int,std::string>,Counts> bins;
    while(file>>q.s>>q.t>>q.k>>q.d) {
        std::string kind=q.d<0?"unreachable":q.d>q.k?"beyond":"within";
        Answer ref=search.run(q);
        for(size_t m=0;m<indices.size();++m) {
            auto a=indices[m].query(g,search,q);
            if(ref.yes!=(q.d>=0 && q.d<=q.k) || a.yes!=ref.yes || a.scans>ref.scans)
                throw std::runtime_error("routing check failed");
            auto& c=bins[{names[m],q.k,kind}];
            ++c.n;c.scans+=a.scans;c.saved+=ref.scans-a.scans;
            c.upper+=a.route=='U';c.lower+=a.route=='L';c.trivial+=a.route=='T';c.fallback+=a.route=='F';
        }
    }
    std::cout<<"method\tk\tdistance_class\tn\tscans\tsaved_vs_bibfs\tupper\tlower\ttrivial\tfallback\n";
    for(auto& [key,c]:bins) {
        auto& [m,k,kind]=key;
        std::cout<<m<<'\t'<<k<<'\t'<<kind<<'\t'<<c.n<<'\t'<<c.scans<<'\t'<<c.saved<<'\t'
                 <<c.upper<<'\t'<<c.lower<<'\t'<<c.trivial<<'\t'<<c.fallback<<'\n';
    }
}
