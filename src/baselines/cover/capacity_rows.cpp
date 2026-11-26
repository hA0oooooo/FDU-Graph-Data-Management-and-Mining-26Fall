// Count necessary row entries, then apply the actual vector growth rule.
#define COVER_CAPACITY_LIBRARY
#include "capacity.cpp"
#include <array>
#include <memory>

using Counts=std::array<std::vector<uint32_t>,2>;

void snapshot(const std::string& path,const std::vector<uint8_t>& roots,
              const Counts& counts,uint64_t root_count,uint64_t end,uint64_t radius,bool pll) {
    std::ofstream out(path+".part",std::ios::binary);
    uint64_t header[]{roots.size(),root_count,end,radius,pll?1ull:0ull};
    out.write("KHOPCAP1",8);
    out.write(reinterpret_cast<const char*>(header),sizeof(header));
    out.write(reinterpret_cast<const char*>(roots.data()),roots.size());
    for(const auto& row:counts)
        out.write(reinterpret_cast<const char*>(row.data()),row.size()*sizeof(uint32_t));
    out.close();
    if(!out)throw std::runtime_error("capacity snapshot write failed");
    if(std::rename((path+".part").c_str(),path.c_str()))throw std::runtime_error("snapshot rename failed");
}

int main(int argc,char** argv) {
    if(argc!=9)throw std::invalid_argument("row-capacity NAME N EDGES cover|pll radius threads memory-gib prefix");
    std::string name=argv[1],family=argv[4],prefix=argv[8];
    int n=std::stoi(argv[2]),radius=std::stoi(argv[5]),threads=std::stoi(argv[6]);
    uint64_t cap=std::stoull(argv[7])<<30;
    bool pll=family=="pll";
    if(!pll && family!="cover")throw std::invalid_argument("cover or pll");
    Adj out(n),in(n);
    std::ifstream graph(argv[3]);
    int u,v;
    while(graph>>u>>v){out.at(u).push_back(v);in.at(v).push_back(u);}
    if(!graph.eof())throw std::runtime_error("invalid graph");
    auto order=root_order(out,in,!pll);
    auto ranks=root_ranks(n,order);
    std::vector<uint8_t> is_root(n);
    for(int r:order)is_root[r]=1;
    omp_set_dynamic(0);
    omp_set_num_threads(threads);
    std::vector<Counts> per_thread(threads);
    std::vector<std::unique_ptr<BitScratch>> scratches(threads);
    #pragma omp parallel
    {
        int id=omp_get_thread_num();
        scratches[id]=std::make_unique<BitScratch>(n);
        for(auto& a:per_thread[id])a.resize(n);
    }
    Counts combined;
    for(auto& a:combined)a.resize(n);
    bool saved_basic=false,saved_plus=false;
    const int chunk=128*threads,roots=order.size();
    std::cerr<<"roots="<<roots<<" radius="<<radius<<" threads="<<threads<<"\n";
    for(int first=0;first<roots;first+=chunk) {
        auto began=Clock::now();
        int stop=std::min(first+chunk,roots);
        #pragma omp parallel for schedule(dynamic,1)
        for(int r=first;r<stop;r+=128) {
            int id=omp_get_thread_num(),count=std::min(128,stop-r);
            auto& scratch=*scratches[id];
            scratch.count(out,in,ranks,order,r,count,radius,pll,nullptr,true,nullptr,&per_thread[id][0]);
            scratch.count(in,out,ranks,order,r,count,radius,pll,nullptr,true,nullptr,&per_thread[id][1]);
        }
        uint64_t basic_entries=0,plus_entries=0,basic_capacity=0,plus_capacity=0;
        #pragma omp parallel for reduction(+:basic_entries,plus_entries,basic_capacity,plus_capacity)
        for(int v=0;v<n;++v) {
            for(int side=0;side<2;++side) {
                uint32_t count=0;
                for(const auto& local:per_thread)count+=local[side][v];
                combined[side][v]=count;
                uint64_t lower=vector_capacity_lower(count);
                plus_entries+=count;plus_capacity+=lower;
                if(is_root[v]){basic_entries+=count;basic_capacity+=lower;}
            }
        }
        std::cout<<name<<'\t'<<family<<'\t'<<roots<<'\t'<<stop<<'\t'<<radius
                 <<'\t'<<basic_entries<<'\t'<<plus_entries<<'\t'<<basic_capacity<<'\t'<<plus_capacity
                 <<'\t'<<std::chrono::duration<double>(Clock::now()-began).count()<<'\n'<<std::flush;
        if(!saved_basic && basic_capacity>cap) {
            snapshot(prefix+(pll?"-pll.bin":"-vcrea.bin"),is_root,combined,roots,stop,radius,pll);
            saved_basic=true;
        }
        if(!pll && !saved_plus && plus_capacity>cap) {
            snapshot(prefix+"-vcrea-plus.bin",is_root,combined,roots,stop,radius,pll);
            saved_plus=true;
        }
        if(saved_basic && (pll || saved_plus))break;
    }
}
