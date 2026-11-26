// Equivalent single-thread canonical label construction using root bit batches.
#define COVER_CAPACITY_LIBRARY
#include "capacity.cpp"

Index packed_index(const Adj& out,const Adj& in,const std::string& method) {
    const bool pll=method=="pll",plus=method=="vcrea-plus";
    if(!pll && !plus && method!="vcrea")throw std::invalid_argument("packed canonical method");
    Index index(out,in,method,1,false);
    const auto ranks=root_ranks(out.size(),index.order);
    BitScratch scratch(out.size());
    const int roots=index.order.size();
    uint64_t scans=0;
    for(int first=0;first<roots;first+=128) {
        int count=std::min(128,roots-first);
        for(int reverse=0;reverse<2;++reverse) {
            std::vector<std::vector<std::pair<int,int>>> records(count);
            const auto& adj=reverse?in:out;
            const auto& opposite=reverse?out:in;
            auto& target=reverse?index.out_labels:index.in_labels;
            scratch.count(adj,opposite,ranks,index.order,first,count,out.size(),pll,&records,plus,&scans);
            for(int i=0;i<count;++i) {
                for(auto [v,distance]:records[i]) {
                    target[v].append(first+i,distance);
                    ++index.entries;
                }
            }
        }
        if(first==0 || (first+count)%1024==0 || first+count==roots) {
            rusage usage{};
            getrusage(RUSAGE_SELF,&usage);
            std::cerr<<"roots="<<first+count<<'/'<<roots<<" labels="<<index.entries
                     <<" peak_kib="<<usage.ru_maxrss<<" packed_scans="<<scans<<'\n';
        }
    }
    index.scans=scans;
    return index;
}

#ifndef PACKED_LABELS_LIBRARY
int main(int argc,char** argv) {
    if(argc!=6 || std::stoi(argv[5])!=1)
        throw std::invalid_argument("packed method N edges queries threshold=1");
    int n=std::stoi(argv[2]);
    Adj out(n),in(n);
    std::ifstream edges(argv[3]),requests(argv[4]);
    int u,v,k;
    while(edges>>u>>v) {out.at(u).push_back(v);in.at(v).push_back(u);}
    std::vector<Query> queries;
    while(requests>>u>>v>>k)queries.push_back({u,v,k});
    if(!edges.eof() || !requests.eof())throw std::runtime_error("invalid input");
    auto start=Clock::now();
    auto index=packed_index(out,in,argv[1]);
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
             <<",\"predictions\":\""<<predictions<<"\",\"builder\":\"packed\"}\n";
}
#endif
