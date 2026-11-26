#define main kreach_cli_main
#include "../src/baselines/kreach/kreach.cpp"
#undef main
#include <random>

int main() {
    int comparisons=0;
    auto check=[&](const Adj& out) {
        const int n=out.size();
        Adj in(n);
        std::vector<std::vector<int>> dist(n,std::vector<int>(n,n+1));
        for(int s=0;s<n;++s) {
            dist[s][s]=0;
            for(int t:out[s]) {
                in[t].push_back(s);
                dist[s][t]=std::min(dist[s][t],1);
            }
        }
        for(int v=0;v<n;++v) for(int s=0;s<n;++s) for(int t=0;t<n;++t)
            dist[s][t]=std::min(dist[s][t],dist[s][v]+dist[v][t]);
        for(int k=2;k<=n+1;++k) {
            KReach index(out,in,k);
            for(int s=0;s<n;++s) for(int t:out[s])
                if(!index.covered[s] && !index.covered[t]) throw std::logic_error("invalid cover");
            for(int s=0;s<n;++s) for(int t=0;t<n;++t) {
                ++comparisons;
                if(index.query(s,t)!=(dist[s][t]<n && dist[s][t]<=k))
                    throw std::logic_error("K-Reach mismatch");
            }
        }
    };
    for(int mask=0;mask<512;++mask) {
        Adj out(3);
        for(int s=0;s<3;++s) for(int t=0;t<3;++t)
            if(mask&(1<<(3*s+t))) out[s].push_back(t);
        check(out);
    }
    std::mt19937 rng(26112026);
    for(int i=0;i<32;++i) {
        Adj out(12);
        for(int s=0;s<12;++s) for(int t=0;t<12;++t)
            if(rng()%5==0) out[s].push_back(t);
        check(out);
    }
    CoreRow sparse, packed;
    sparse.sparse={0u<<2|2u, 20u<<2|0u, 40u<<2|1u};
    packed.sparse={0u<<2|2u, 20u<<2|0u, 40u<<2|1u};
    sparse.finish(64); packed.finish(41);
    if (sparse.sparse.empty() || packed.packed.empty()) throw std::logic_error("row layout not exercised");
    for(uint32_t r=0;r<41;++r)
        if(sparse.tier(r)!=packed.tier(r)) throw std::logic_error("packing changed tier");
    std::cout<<comparisons<<" K-Reach comparisons passed\n";
}
