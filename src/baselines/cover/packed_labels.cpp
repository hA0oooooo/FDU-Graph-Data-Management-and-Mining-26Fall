// Equivalent single-thread canonical label construction using root bit batches.
#define COVER_CAPACITY_LIBRARY
#include "capacity.cpp"
#include <memory>

Index packed_index(const Adj& out,const Adj& in,const std::string& method,int threads=1) {
    const bool pll=method=="pll",plus=method=="vcrea-plus";
    if(!pll && !plus && method!="vcrea")throw std::invalid_argument("packed canonical method");
    if(threads<1)throw std::invalid_argument("positive build thread count");
    Index index(out,in,method,1,false);
    const auto ranks=root_ranks(out.size(),index.order);
    omp_set_dynamic(0);
    omp_set_num_threads(threads);
    std::vector<std::unique_ptr<BitScratch>> scratch(threads);
    #pragma omp parallel
    {
        scratch[omp_get_thread_num()]=std::make_unique<BitScratch>(out.size());
    }
    const int roots=index.order.size(),wave=128*threads;
    uint64_t scans=0;
    for(int first=0;first<roots;first+=wave) {
        int stop=std::min(first+wave,roots),groups=(stop-first+127)/128;
        for(int reverse=0;reverse<2;++reverse) {
            using Records=std::vector<std::vector<std::pair<int,int>>>;
            std::vector<Records> staged(groups);
            const auto& adj=reverse?in:out;
            const auto& opposite=reverse?out:in;
            auto& target=reverse?index.out_labels:index.in_labels;
            uint64_t scanned=0;
            #pragma omp parallel for schedule(dynamic,1) reduction(+:scanned)
            for(int group=0;group<groups;++group) {
                int begin=first+128*group,count=std::min(128,stop-begin);
                staged[group].resize(count);
                uint64_t local=0;
                scratch[omp_get_thread_num()]->count(adj,opposite,ranks,index.order,begin,count,
                     out.size(),pll,&staged[group],plus,&local);
                scanned+=local;
            }
            scans+=scanned;
            for(int group=0;group<groups;++group) {
                int begin=first+128*group;
                for(int i=0;i<int(staged[group].size());++i)
                    for(auto [v,distance]:staged[group][i]) {
                        target[v].append(begin+i,distance);
                        ++index.entries;
                    }
            }
        }
        if(first==0 || stop%1024==0 || stop==roots) {
            rusage usage{};
            getrusage(RUSAGE_SELF,&usage);
            std::cerr<<"roots="<<stop<<'/'<<roots<<" labels="<<index.entries
                     <<" peak_kib="<<usage.ru_maxrss<<" packed_scans="<<scans<<'\n';
        }
    }
    index.scans=scans;
    return index;
}

#ifndef PACKED_LABELS_LIBRARY
int main(int argc,char** argv) {
    if((argc!=6 && argc!=7) || std::stoi(argv[5])!=1)
        throw std::invalid_argument("packed method N edges queries threshold=1");
    int n=std::stoi(argv[2]),threads=argc==7?std::stoi(argv[6]):1;
    Adj out(n),in(n);
    std::ifstream edges(argv[3]),requests(argv[4]);
    int u,v,k;
    while(edges>>u>>v) {out.at(u).push_back(v);in.at(v).push_back(u);}
    std::vector<Query> queries;
    while(requests>>u>>v>>k)queries.push_back({u,v,k});
    if(!edges.eof() || !requests.eof())throw std::runtime_error("invalid input");
    auto start=Clock::now();
    auto index=packed_index(out,in,argv[1],threads);
    auto built=Clock::now();
    std::string predictions(queries.size(),'0');
    auto query_start=Clock::now();
    for(size_t i=0;i<queries.size();++i) {
        const auto& q=queries[i];
        predictions[i]+=index.query(q.s,q.t,q.k);
    }
    auto end=Clock::now();
    int64_t bytes=0,capacity=0;
    for(const auto* labels:{&index.out_labels,&index.in_labels})
        for(const auto& row:*labels){bytes+=row.bytes.size();capacity+=row.bytes.capacity();}
    rusage usage{};
    getrusage(RUSAGE_SELF,&usage);
    auto ns=[](auto a,auto b){return std::chrono::duration_cast<std::chrono::nanoseconds>(b-a).count();};
    std::cout<<"{\"hubs\":"<<index.order.size()<<",\"labels\":"<<index.entries
             <<",\"encoded_bytes\":"<<bytes<<",\"vector_capacity_bytes\":"<<capacity
             <<",\"build_scans\":"<<index.scans<<",\"build_ns\":"<<ns(start,built)
             <<",\"query_ns\":"<<ns(query_start,end)<<",\"process_peak_kib\":"<<usage.ru_maxrss
             <<",\"predictions\":\""<<predictions<<"\",\"builder\":\"packed\",\"build_threads\":"<<threads<<"}\n";
}
#endif
