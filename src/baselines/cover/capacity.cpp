// Count a provable subset of the canonical labels without storing the full index.
// A clean vertex has no shortest path from the current root through an earlier hub.
#define main label_program_main
#include "labels.cpp"
#undef main
#include <omp.h>

struct LabelCounts {
    uint64_t basic=0, plus=0;
    LabelCounts& operator+=(const LabelCounts& other) {
        basic+=other.basic; plus+=other.plus; return *this;
    }
};


// libstdc++ vector<uint8_t> grows from zero by doubling when append exhausts
// capacity; every necessary label contributes at least two appended bytes.
uint64_t vector_capacity_lower(uint64_t entries) {
    if(!entries)return 0;
    uint64_t required=2*entries;
    return uint64_t{1}<<(64-__builtin_clzll(required-1));
}

struct Scratch {
    std::vector<int> stamp, depth, queue;
    std::vector<char> clean;
    int epoch=0;
    explicit Scratch(size_t n):stamp(n),depth(n),queue(n),clean(n) {}

    LabelCounts count(const Adj& adj,const Adj& opposite,const std::vector<int>& ranks,
                      int root,int radius,bool pll) {
        ++epoch;
        int r=ranks[root],head=0,tail=1;
        queue[0]=root; stamp[root]=epoch; depth[root]=0; clean[root]=1;
        LabelCounts counts;
        for(int layer=0;head<tail && layer<=radius;++layer) {
            int end=tail;
            bool any_clean=false;
            for(int i=head;i<end;++i) {
                int u=queue[i];
                if(!clean[u])continue;
                any_clean=true;
                bool receiver=pll || ranks[u]<static_cast<int>(ranks.size());
                counts.basic+=receiver;
                counts.plus+=receiver || opposite[u].size()>1;
            }
            if(!any_clean || layer==radius)break;
            for(;head<end;++head) {
                int u=queue[head];
                for(int v:adj[u]) {
                    bool good=clean[u] && ranks[v]>=r;
                    if(stamp[v]!=epoch) {
                        stamp[v]=epoch; depth[v]=layer+1; clean[v]=good; queue[tail++]=v;
                    } else if(depth[v]==layer+1 && !good) clean[v]=0;
                }
            }
        }
        return counts;
    }
};

std::vector<int> root_ranks(size_t n,const std::vector<int>& order) {
    std::vector<int> ranks(n,static_cast<int>(n));
    for(size_t i=0;i<order.size();++i)ranks[order[i]]=i;
    return ranks;
}

LabelCounts root_counts(const Adj& out,const Adj& in,const std::vector<int>& ranks,
                       int root,int radius,bool pll,Scratch& scratch) {
    auto counts=scratch.count(out,in,ranks,root,radius,pll);
    counts+=scratch.count(in,out,ranks,root,radius,pll);
    return counts;
}

// Propagate up to 128 independent roots in one traversal. A bit is dirty if
// at least one shortest path from that root contains an earlier-ranked hub.
struct BitScratch {
    std::vector<__uint128_t> seen,front,dirty,next,next_dirty;
    std::vector<int> active, following;
    explicit BitScratch(size_t n):seen(n),front(n),dirty(n),next(n),next_dirty(n) {
        active.reserve(n);following.reserve(n);
    }

    LabelCounts count(const Adj& adj,const Adj& opposite,const std::vector<int>& ranks,
                      const std::vector<int>& order,int first,int count,int radius,bool pll,
                      std::vector<std::vector<std::pair<int,int>>>* records=nullptr,
                      bool collect_plus=false,uint64_t* edge_scans=nullptr,
                      std::vector<uint32_t>* row_counts=nullptr,int record_shards=1) {
        const size_t shard_width=(ranks.size()+record_shards-1)/record_shards;
        std::fill(seen.begin(),seen.end(),0);
        const __uint128_t mask=count==128?~__uint128_t{0}:((__uint128_t{1}<<count)-1);
        __uint128_t alive=mask;
        active.clear();
        for(int i=0;i<count;++i) {
            int u=order[first+i]; __uint128_t bit=__uint128_t{1}<<i;
            front[u]=seen[u]=bit; active.push_back(u);
        }
        LabelCounts total;
        for(int layer=0;!active.empty() && layer<=radius;++layer) {
            __uint128_t has_clean=0;
            for(int u:active) {
                __uint128_t good=front[u]&alive&~dirty[u];
                has_clean|=good;
                unsigned number=__builtin_popcountll(static_cast<uint64_t>(good)) + __builtin_popcountll(static_cast<uint64_t>(good>>64));
                bool receiver=pll || ranks[u]<static_cast<int>(ranks.size());
                if(receiver)total.basic+=number;
                bool plus_receiver=receiver || opposite[u].size()>1;
                if(plus_receiver)total.plus+=number;
                if(row_counts && (collect_plus?plus_receiver:receiver)) (*row_counts)[u]+=number;
                if(records && (collect_plus?plus_receiver:receiver)) {
                    size_t base=(size_t(u)/shard_width)*count;
                    for(int part=0;part<2;++part) {
                        uint64_t bits=static_cast<uint64_t>(good>>(64*part));
                        while(bits) {
                            int rank=64*part+__builtin_ctzll(bits);
                            (*records)[base+rank].emplace_back(u,layer);
                            bits&=bits-1;
                        }
                    }
                }
            }
            alive&=has_clean;
            if(!alive || layer==radius) {
                for(int u:active)front[u]=dirty[u]=0;
                break;
            }
            following.clear();
            for(int u:active) {
                __uint128_t bits=front[u]&alive,bad=dirty[u]&bits;
                front[u]=dirty[u]=0;
                if(!bits)continue;
                if(edge_scans)*edge_scans+=adj[u].size();
                for(int v:adj[u]) {
                    __uint128_t fresh=bits&~seen[v];
                    if(!fresh)continue;
                    if(!next[v])following.push_back(v);
                    next[v]|=fresh;
                    next_dirty[v]|=bad&fresh;
                }
            }
            for(int v:following) {
                int offset=ranks[v]-first;
                __uint128_t earlier=offset<0?mask:offset>=count-1?0:mask&(~__uint128_t{0}<<(offset+1));
                front[v]=next[v];
                dirty[v]=(next_dirty[v]|(next[v]&earlier))&next[v];
                seen[v]|=next[v];
                next[v]=next_dirty[v]=0;
            }
            active.swap(following);
        }
        return total;
    }
};

LabelCounts group_counts(const Adj& out,const Adj& in,const std::vector<int>& ranks,
                         const std::vector<int>& order,int first,int count,int radius,bool pll,
                         BitScratch& scratch) {
    auto counts=scratch.count(out,in,ranks,order,first,count,radius,pll);
    counts+=scratch.count(in,out,ranks,order,first,count,radius,pll);
    return counts;
}

#ifndef COVER_CAPACITY_LIBRARY
int main(int argc,char** argv) {
    if(argc!=9) throw std::invalid_argument("capacity graph N edges cover|pll start end radius threads");
    const std::string name=argv[1];
    int n=std::stoi(argv[2]);
    Adj out(n),in(n);
    std::ifstream graph(argv[3]);
    int s,t;
    while(graph>>s>>t) {out.at(s).push_back(t);in.at(t).push_back(s);}
    if(!graph.eof())throw std::runtime_error("unreadable graph");
    const std::string method=argv[4];
    const bool pll=method=="pll";
    if(!pll && method!="cover")throw std::invalid_argument("expected cover or pll");
    auto order=root_order(out,in,!pll);
    auto ranks=root_ranks(n,order);
    int start=std::stoi(argv[5]),end=std::min(std::stoi(argv[6]),static_cast<int>(order.size()));
    int radius=std::stoi(argv[7]),threads=std::stoi(argv[8]);
    if(start<0 || start>=end || radius<0 || threads<1)throw std::invalid_argument("empty or invalid range");
    omp_set_num_threads(threads);
    std::cerr<<"roots="<<order.size()<<" start="<<start<<" end="<<end<<" radius="<<radius<<"\n";
    const int chunk=128*threads;
    for(int first=start;first<end;first+=chunk) {
        auto began=Clock::now();
        uint64_t basic=0,plus=0;
        int stop=std::min(first+chunk,end);
        #pragma omp parallel reduction(+:basic,plus)
        {
            BitScratch scratch(n);
            #pragma omp for schedule(dynamic,1)
            for(int r=first;r<stop;r+=128) {
                auto counts=group_counts(out,in,ranks,order,r,std::min(128,stop-r),radius,pll,scratch);
                basic+=counts.basic; plus+=counts.plus;
            }
        }
        std::cout<<name<<'\t'<<method<<'\t'<<order.size()<<'\t'<<first<<'\t'<<stop<<'\t'
                 <<radius<<'\t'<<basic<<'\t'<<plus<<'\t'
                 <<std::chrono::duration<double>(Clock::now()-began).count()<<'\n'<<std::flush;
    }
}
#endif
