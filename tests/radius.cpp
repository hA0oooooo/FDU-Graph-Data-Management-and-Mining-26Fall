#include "../src/radius/hotspot.hpp"
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
    Graph suffix(6,{{0,1},{1,2},{2,3},{3,4},{4,5}});
    std::vector<Node> root{2};
    Profiles small{explore(suffix.side[0],2,2),explore(suffix.side[1],2,2)};
    HotIndex local(small,{2,2},root,suffix.n);
    assert(local.decide(2,1,2,2,4)==1);
    assert(local.decide(2,1,2,2,5)==-1);
    assert(local.decide(2,1,2,3,5)==0);
    assert(local.decide(2,0,1,2,0)==1);
    Search via(suffix);
    assert(via.guided(Query{0,5,5,5},local,false).yes);
    assert(!via.guided(Query{0,5,4,5},local,false).yes);
    assert(via.guided(Query{0,4,4,4},local,false).route=='U');
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
        std::sort(roots.begin(),roots.end()); p.clear();
        for(auto u:roots) for(int dir:{0,1}) p.push_back(explore(g.side[dir],u,max_radius));
        auto uniform_active=allocate(p,12,qs,weights,2);
        for (int h:uniform_active) assert(h==0 || h==2);
        for (auto cfg:{Config(6,0),Config{0,2,1,0,3,2},structural(p,12),uniform_active,allocate(p,12,qs,weights)}) {
            Index packed(p,roots,cfg), fresh(g,roots,cfg);
            HotIndex hotspot(p,cfg,roots,g.n);
            for (auto& q:qs) {
                assert(hotspot.query(search,q).yes==(q.d<=q.k));
                assert(search.guided(q,hotspot,false).yes==(q.d<=q.k));
                assert(packed.query(g,search,q).yes==(q.d<=q.k));
                assert(fresh.query(g,search,q).yes==(q.d<=q.k)); ++checked;
            }
        }
    }
    std::cout<<checked<<" index/config/query combinations verified against Floyd-Warshall\n";
}
