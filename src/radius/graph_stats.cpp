#include "graph.hpp"
#include <iostream>
#include <iomanip>
using namespace khop;

int main(int argc, char** argv) {
    if (argc != 4) throw std::invalid_argument("graph_stats name N edges");
    const auto g=Graph::load(std::stoul(argv[2]),argv[3]);
    const auto& out=g.side[1];
    const auto& in=g.side[0];
    std::vector<char> seen(g.n);
    std::vector<Node> finish;
    finish.reserve(g.n);
    std::vector<std::pair<Node,uint32_t>> stack;
    for (Node start=0;start<g.n;++start) {
        if (seen[start]) continue;
        seen[start]=1; stack.emplace_back(start,out.offsets[start]);
        while (!stack.empty()) {
            auto& [u,j]=stack.back();
            if (j==out.offsets[u+1]) {
                finish.push_back(u); stack.pop_back(); continue;
            }
            Node v=out.neighbors[j++];
            if (!seen[v]) { seen[v]=1; stack.emplace_back(v,out.offsets[v]); }
        }
    }
    std::fill(seen.begin(),seen.end(),0);
    std::vector<Node> q;
    unsigned components=0, largest=0;
    for (auto it=finish.rbegin();it!=finish.rend();++it) {
        Node start=*it;
        if (seen[start]) continue;
        ++components; q.assign(1,start); seen[start]=1;
        for (size_t i=0;i<q.size();++i) {
            Node u=q[i];
            for (auto j=in.offsets[u];j<in.offsets[u+1];++j) {
                Node v=in.neighbors[j];
                if (!seen[v]) { seen[v]=1; q.push_back(v); }
            }
        }
        largest=std::max(largest,static_cast<unsigned>(q.size()));
    }
    Count self=0, reciprocal=0, zero_out=0, zero_in=0;
    unsigned max_out=0, max_in=0;
    std::vector<unsigned> degrees; degrees.reserve(g.n);
    for (Node u=0;u<g.n;++u) {
        zero_out+=!out.degree(u); zero_in+=!in.degree(u);
        max_out=std::max(max_out,out.degree(u)); max_in=std::max(max_in,in.degree(u));
        degrees.push_back(out.degree(u));
        for (auto j=out.offsets[u];j<out.offsets[u+1];++j) {
            Node v=out.neighbors[j];
            if (u==v) { ++self; continue; }
            auto a=out.neighbors.begin()+out.offsets[v], b=out.neighbors.begin()+out.offsets[v+1];
            reciprocal+=std::binary_search(a,b,u);
        }
    }
    std::sort(degrees.begin(),degrees.end());
    Count m=out.neighbors.size();
    std::cout<<argv[1]<<'\t'<<g.n<<'\t'<<m<<'\t'<<self<<'\t'
             <<components<<'\t'<<largest<<'\t'<<zero_out<<'\t'<<zero_in<<'\t'
             <<degrees[g.n/2]<<'\t'<<max_out<<'\t'<<max_in<<'\t'<<reciprocal<<'\t'
             <<std::setprecision(10)<<double(m)/g.n<<'\t'<<double(m-self)/(double(g.n)*(g.n-1))<<'\n';
}
