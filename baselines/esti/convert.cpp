// Convert a sorted dense edge list to the author's per-vertex adjacency input.
#include <fstream>
#include <iostream>
#include <vector>
int main(int argc,char** argv) {
    if (argc!=4) return 2;
    int n=std::stoi(argv[1]), m=std::stoi(argv[2]);
    std::ifstream f(argv[3]); if (!f) return 2;
    std::cout<<n<<'\n'<<m<<'\n';
    int u,v,count=0;
    bool more=bool(f>>u>>v);
    std::vector<int> neighbors;
    for(int i=0;i<n;++i) {
        neighbors.clear();
        while(more && u==i) {
            neighbors.push_back(v); ++count; more=bool(f>>u>>v);
        }
        std::cout<<i<<' '<<neighbors.size();
        for(auto w:neighbors) std::cout<<' '<<w;
        std::cout<<'\n';
    }
    return more || count!=m || !std::cout;
}
