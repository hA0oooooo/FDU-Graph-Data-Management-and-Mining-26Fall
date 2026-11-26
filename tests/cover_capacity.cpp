#define COVER_CAPACITY_LIBRARY
#include "../src/baselines/cover/capacity.cpp"
#include <random>

int main() {
    unsigned graphs=0;
    auto check=[&](const Adj& out) {
        Adj in(out.size());
        for(int u=0;u<int(out.size());++u)for(int v:out[u])in[v].push_back(u);
        for(bool pll:{false,true}) {
            auto order=root_order(out,in,!pll);
            auto ranks=root_ranks(out.size(),order);
            Scratch scratch(out.size());
            LabelCounts result,shorter;
            for(int r:order) {
                result+=root_counts(out,in,ranks,r,out.size(),pll,scratch);
                shorter+=root_counts(out,in,ranks,r,2,pll,scratch);
            }
            BitScratch bits(out.size());
            LabelCounts parallel,parallel_short;
            for(int first=0;first<int(order.size());first+=64) {
                int count=std::min(64,int(order.size())-first);
                parallel+=group_counts(out,in,ranks,order,first,count,out.size(),pll,bits);
                parallel_short+=group_counts(out,in,ranks,order,first,count,2,pll,bits);
            }
            if(parallel.basic!=result.basic || parallel.plus!=result.plus ||
               parallel_short.basic!=shorter.basic || parallel_short.plus!=shorter.plus)
                throw std::logic_error("packed count differs from scalar witness count");
            Index basic(out,in,pll?"pll":"vcrea",1);
            if(result.basic!=uint64_t(basic.entries) || shorter.basic>result.basic)
                throw std::logic_error("canonical label count differs from full solver");
            if(!pll) {
                Index plus(out,in,"vcrea-plus",1);
                if(result.plus!=uint64_t(plus.entries) || shorter.plus>result.plus)
                    throw std::logic_error("canonical VCRea+ count differs");
            }
        }
        ++graphs;
    };
    for(int mask=0;mask<512;++mask) {
        Adj out(3);
        for(int u=0;u<3;++u)for(int v=0;v<3;++v)if(mask&(1<<(3*u+v)))out[u].push_back(v);
        check(out);
    }
    std::mt19937 random(26112026);
    for(int i=0;i<48;++i) {
        Adj out(12);
        for(int u=0;u<12;++u)for(int v=0;v<12;++v)if(random()%5==0)out[u].push_back(v);
        check(out);
    }
    for(int i=0;i<4;++i) {
        Adj out(130);
        for(int u=0;u<130;++u)for(int v=0;v<130;++v)if(random()%21==0)out[u].push_back(v);
        check(out);
    }
    std::cout<<graphs<<" graphs: exact canonical label counts agree with all three constructors\n";
}
