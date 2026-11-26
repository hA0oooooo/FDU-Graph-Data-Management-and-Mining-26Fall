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
            Index packed=packed_index(out,in,method);
            if(scalar.entries!=packed.entries || scalar.order!=packed.order)
                throw std::logic_error("packed root or label count mismatch");
            for(size_t v=0;v<out.size();++v) {
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
    std::cout<<checked<<" full index byte comparisons passed\n";
}
