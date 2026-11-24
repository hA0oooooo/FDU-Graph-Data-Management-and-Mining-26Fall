#include "../src/radius/index.hpp"
#include "../src/radius/filters.hpp"
#include <cassert>
#include <iostream>
using namespace khop;

int main() {
    // Neither one-sided upgrade alone certifies 0 -> 2 through landmark 1.
    Graph chain(3,{{0,1},{1,2}});
    Profiles balls={explore(chain.side[0],1,max_radius),explore(chain.side[1],1,max_radius)};
    std::vector<Query> training={{0,2,2,2}};
    auto paired=allocate(balls,4,training,{50});
    assert((paired==Config{1,1}));
    assert((allocate(balls,3,training,{50})==Config{0,0}));
    assert((allocate(balls,4,training,{3})==Config{0,0}));
    Count checked=0;
    for (int mask=0;mask<512;++mask) {
        std::vector<std::pair<Node,Node>> edges;
        int d[3][3];
        for (Node i=0;i<3;++i) for (Node j=0;j<3;++j) {
            if (mask&(1<<(3*i+j))) edges.emplace_back(i,j);
            d[i][j]=i==j?0:mask&(1<<(3*i+j))?1:99;
        }
        for (int m=0;m<3;++m) for (int i=0;i<3;++i) for (int j=0;j<3;++j)
            d[i][j]=std::min(d[i][j],d[i][m]+d[m][j]);
        Graph g(3,edges); Search search(g);
        auto roots=landmarks(g); Profiles p;
        for (auto u:roots) for(int dir:{0,1}) p.push_back(explore(g.side[dir],u,max_radius));
        std::vector<Query> qs;
        std::vector<unsigned> weights;
        for(Node s=0;s<3;++s) for(Node t=0;t<3;++t) for(int k=0;k<=4;++k) {
            Query q{s,t,k,d[s][t]};
            assert(search.run(q).yes==(d[s][t]<=k));
            assert(search.run(q,false).yes==(d[s][t]<=k));
            qs.push_back(q); weights.push_back(50);
        }
        Topology topo(g); CoverTree tree(g);
        for (auto q:qs) {
            assert(!topo.witness(g,q) || q.d>q.k);
            assert(!tree.witness(g,q) || q.d<=q.k);
        }
        for (auto cfg:{Config(6,0),Config{0,2,1,0,3,2},structural(p,12),allocate(p,12,qs,weights)}) {
            Index packed(p,roots,cfg), fresh(g,roots,cfg);
            for (auto& q:qs) {
                assert(packed.query(g,search,q).yes==(q.d<=q.k));
                assert(fresh.query(g,search,q).yes==(q.d<=q.k)); ++checked;
            }
        }
    }
    std::cout<<checked<<" index/config/query combinations verified against Floyd-Warshall\n";
}
