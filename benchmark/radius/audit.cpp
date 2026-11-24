#include "../../src/radius/graph.hpp"
#include <iostream>
using namespace khop;
int main(int argc,char** argv) {
    if(argc!=4)return 2;
    auto g=Graph::load(std::stoul(argv[1]),argv[2]); const auto& rev=g.side[0];
    std::cout<<"split\tclass\tchecked\n";
    for(std::string split:{"train","validation","test"}) {
        std::ifstream file(std::string(argv[3])+"/"+split+".tsv");
        std::string header;std::getline(file,header);Query q;unsigned counts[3]={};
        while(file>>q.s>>q.t>>q.k>>q.d) {
            int bin=q.d<0?2:q.d>q.k?1:0;
            if(counts[bin]>=2)continue;
            ++counts[bin];
            std::vector<int> d(g.n,-1);d[q.t]=0;
            std::vector<Node> frontier{q.t};
            for(size_t j=0;j<frontier.size() && d[q.s]<0;++j) {
                Node u=frontier[j];
                for(auto i=rev.offsets[u];i<rev.offsets[u+1];++i) {
                    Node v=rev.neighbors[i];
                    if(d[v]<0) {d[v]=d[u]+1;frontier.push_back(v);}
                }
            }
            if(d[q.s]!=q.d)throw std::runtime_error("independent reverse distance mismatch");
        }
        for(int b=0;b<3;++b) std::cout<<split<<'\t'<<b<<'\t'<<counts[b]<<'\n';
    }
}
