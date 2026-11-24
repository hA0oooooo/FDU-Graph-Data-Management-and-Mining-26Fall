#define main scalable_cli_main
#include "scalable.cpp"
#undef main
#include <random>

int main() {
    long long comparisons=0, corrected=0, inserted=0;
    auto check=[&](Graph g, int b, int cap) {
        int n=g.out.size();
        for (auto* adj : {&g.out,&g.in})
            for (auto& row : *adj) std::sort(row.begin(),row.end());
        vector<vector<int>> d(n,vector<int>(n,INF));
        for (int s=0;s<n;++s) {
            d[s][s]=0;
            for (int t : g.out[s]) d[s][t]=std::min(d[s][t],1);
        }
        for (int v=0;v<n;++v) for (int s=0;s<n;++s) for (int t=0;t<n;++t)
            d[s][t]=std::min(d[s][t],d[s][v]+d[v][t]);
        for (int radius : {0,1,2,3,n}) {
            Index idx(g,radius,b,cap);
            corrected+=idx.lowered;
            inserted+=idx.added;
            for (int s=0;s<n;++s) for (int t=0;t<n;++t) {
                int lo=radius==n?0:radius, hi=radius==n?n+2:radius;
                for (int k=lo;k<=hi;++k) {
                    ++comparisons;
                    if (idx.query(s,t,k)!=(d[s][t]<=k)) throw std::logic_error("Floyd mismatch");
                }
            }
        }
    };
    for (int mask=0;mask<512;++mask) {
        Graph g(3);
        for (int s=0;s<3;++s) for (int t=0;t<3;++t)
            if (mask & (1<<(3*s+t))) g.add(s,t);
        for (int b : {0,1,3}) for (int cap : {0,2}) check(g,b,cap);
    }
    std::mt19937 rng(260711);
    for (int graph=0;graph<128;++graph) {
        Graph g(9);
        for (int s=0;s<9;++s) for (int t=0;t<9;++t) if (rng()%7==0) g.add(s,t);
        check(g,1,4);
    }
    // Two competing u -> v routes: 2 via p and 3 entirely in G-S.
    Graph example(11);
    for (auto [s,t] : vector<std::pair<int,int>>{
            {1,0},{0,2},{1,3},{3,4},{4,2},{5,2},{1,6},{1,7},{0,8},{0,9},{0,10}})
        example.add(s,t);
    check(example,1,5);
    Index corrected_example(example,3,1,5);
    if (!corrected_example.lowered || corrected_example.second.through(1,2,-1)!=2 ||
        !corrected || !inserted) throw std::logic_error("cross-layer correction untested");
    std::cout<<"{\"exhaustive_graphs\":512,\"random_graphs\":128,\"designed_graphs\":1,"
             <<"\"oracle_comparisons\":"<<comparisons<<",\"d2_lowered\":"<<corrected
             <<",\"d2_inserted\":"<<inserted<<",\"errors\":0}\n";
}
