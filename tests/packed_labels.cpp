#define PACKED_LABELS_LIBRARY
#include "../src/baselines/cover/packed_labels.cpp"
#include <random>

int main() {
    unsigned checked=0;
    auto verify=[&](const Adj& out) {
        Adj in(out.size());
        for(int u=0;u<int(out.size());++u)for(int v:out[u])in[v].push_back(u);
        for(auto method:{"vcrea","vcrea-plus","pll"}) {
            Index scalar(out,in,method,1);
            Index packed=packed_index(out,in,method,out.size()>=130?4:1);
            if(scalar.entries!=packed.entries || scalar.order!=packed.order)
                throw std::logic_error("packed root or label count mismatch");
            for(int percentage:{0,25,50,100}) {
                auto hybrid=packed_index(out,in,method,out.size()>=130?4:1,percentage);
                if(hybrid.entries!=scalar.entries || hybrid.order!=scalar.order)
                    throw std::logic_error("hybrid root or entry count mismatch");
                for(size_t v=0;v<out.size();++v)
                    if(scalar.out_labels[v].bytes!=hybrid.out_labels[v].bytes || scalar.in_labels[v].bytes!=hybrid.in_labels[v].bytes ||
                       scalar.out_labels[v].bytes.capacity()!=hybrid.out_labels[v].bytes.capacity() ||
                       scalar.in_labels[v].bytes.capacity()!=hybrid.in_labels[v].bytes.capacity())
                        throw std::logic_error("hybrid index bytes differ");
            }
            auto ranks=root_ranks(out.size(),packed.order);
            BitScratch scratch(out.size());
            std::vector<uint32_t> forward_counts(out.size()),reverse_counts(out.size());
            for(int first=0;first<int(packed.order.size());first+=128) {
                int count=std::min(128,int(packed.order.size())-first);
                bool pll=std::string(method)=="pll",plus=std::string(method)=="vcrea-plus";
                scratch.count(out,in,ranks,packed.order,first,count,out.size(),pll,nullptr,plus,nullptr,&forward_counts);
                scratch.count(in,out,ranks,packed.order,first,count,out.size(),pll,nullptr,plus,nullptr,&reverse_counts);
            }
            for(size_t v=0;v<out.size();++v) {
                uint32_t exact_in=0,exact_out=0;
                for(Cursor c(scalar.in_labels[v]);c.next();)++exact_in;
                for(Cursor c(scalar.out_labels[v]);c.next();)++exact_out;
                if(forward_counts[v]!=exact_in || reverse_counts[v]!=exact_out)
                    throw std::logic_error("row witness count differs from the full labels");
                if(vector_capacity_lower(forward_counts[v])>scalar.in_labels[v].bytes.capacity() ||
                   vector_capacity_lower(reverse_counts[v])>scalar.out_labels[v].bytes.capacity())
                    throw std::logic_error("row-vector lower bound exceeded actual capacity");
                if(scalar.out_labels[v].bytes!=packed.out_labels[v].bytes ||
                   scalar.in_labels[v].bytes!=packed.in_labels[v].bytes)
                    throw std::logic_error("packed label bytes differ from scalar");
            }
            ++checked;
        }
    };
    for(int mask=0;mask<512;++mask) {
        Adj out(3);
        for(int u=0;u<3;++u)for(int v=0;v<3;++v)if(mask&(1<<(3*u+v)))out[u].push_back(v);
        verify(out);
    }
    std::mt19937 rng(26112026);
    for(int n:{12,130,301})for(int iter=0;iter<5;++iter) {
        Adj out(n);
        for(int u=0;u<n;++u)for(int v=0;v<n;++v)if(rng()%(n/3+1)==0)out[u].push_back(v);
        verify(out);
    }
    Adj chain(301);
    for(int u=0;u<300;++u)chain[u].push_back(u+1);
    verify(chain);
    Adj multiple_waves(1051);
    for(int u=0;u<1051;++u) {
        multiple_waves[u].push_back((u+1)%1051);
        multiple_waves[u].push_back((u+73)%1051);
    }
    verify(multiple_waves);
    std::cout<<checked<<" full index byte comparisons passed\n";
}
