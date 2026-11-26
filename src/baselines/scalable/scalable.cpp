#include "../../benchmark_metrics.hpp"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

using std::vector;
using Clock = std::chrono::steady_clock;
constexpr int INF = 1000000000;

struct Graph {
    vector<vector<int>> out, in;
    explicit Graph(int n) : out(n), in(n) {}
    void add(int u, int v) { out.at(u).push_back(v); in.at(v).push_back(u); }
    void remove_hubs(const vector<int>& rank) {
        for (auto* adj : {&out,&in}) for (int u=0; u<int(rank.size()); ++u) {
            auto& row=(*adj)[u];
            if (rank[u]>=0) vector<int>().swap(row);
            else row.erase(std::remove_if(row.begin(),row.end(),[&](int v){ return rank[v]>=0; }),row.end());
        }
    }

    template<class Visit>
    void visit_neighbors(int u, Visit visit) const {
        const auto& a=out[u];
        const auto& b=in[u];
        size_t i=0, j=0;
        while (i<a.size() || j<b.size()) {
            int x=i<a.size()?a[i]:INF, y=j<b.size()?b[j]:INF;
            visit(std::min(x,y));
            if (x<=y) ++i;
            if (y<=x) ++j;
        }
    }
};

struct Label { int hub, distance; };
struct Layer {
    vector<int> rank, hubs;
    vector<vector<Label>> to_hub, from_hub;
    vector<vector<int>> core;
    long long bfs_scans = 0, omitted = 0, endpoint_labels = 0;
    explicit Layer(int n) : rank(n,-1), to_hub(n), from_hub(n) {}

    uint64_t allocated_bytes() const {
        uint64_t bytes=(rank.capacity()+hubs.capacity())*sizeof(int)
            +(to_hub.capacity()+from_hub.capacity())*sizeof(vector<Label>)
            +core.capacity()*sizeof(vector<int>);
        for(const auto& row:to_hub)bytes+=row.capacity()*sizeof(Label);
        for(const auto& row:from_hub)bytes+=row.capacity()*sizeof(Label);
        for(const auto& row:core)bytes+=row.capacity()*sizeof(int);
        return bytes;
    }

    // Minimum length routed via this layer. Decision queries may stop at any witness.
    int through(int s, int t, int stop) const {
        int a = rank[s], b = rank[t];
        if (a >= 0 && b >= 0) return core[a][b];
        int best = INF;
        if (a >= 0) {
            for (Label y : from_hub[t]) {
                best = std::min(best, core[a][y.hub] + y.distance);
                if (best <= stop) break;
            }
        } else if (b >= 0) {
            for (Label x : to_hub[s]) {
                best = std::min(best, x.distance + core[x.hub][b]);
                if (best <= stop) break;
            }
        } else {
            for (Label x : to_hub[s]) {
                for (Label y : from_hub[t]) {
                    best = std::min(best, x.distance + core[x.hub][y.hub] + y.distance);
                    if (best <= stop) return best;
                }
            }
        }
        return best;
    }

    void build(const Graph& g, int radius, int limit, vector<char>& covered,
               const vector<int>& excluded, bool stop_on_coverage) {
        int n = rank.size();
        vector<int> score(n,0), depth(n,-1), queue;
        vector<char> old_hub_on_path(n,0);
        int uncovered = 0;
        for (int u = 0; u < n; ++u) {
            if (!excluded.empty() && excluded[u] >= 0) continue;
            g.visit_neighbors(u,[&](int v){ score[u] += !covered[v]; });
            uncovered += !covered[u];
        }
        auto cover = [&](int u) {
            if (covered[u]) return;
            covered[u]=1;
            --uncovered;
            g.visit_neighbors(u,[&](int v){ --score[v]; });
        };
        for (int i = 0; i < limit && (!stop_on_coverage || uncovered); ++i) {
            int r = -1;
            for (int u = 0; u < n; ++u) {
                if ((!excluded.empty() && excluded[u]>=0) || rank[u]>=0) continue;
                // Prefer an uncovered candidate on equal score so isolated vertices make progress.
                if (r < 0 || score[u] > score[r] ||
                    (score[u]==score[r] && covered[r] && !covered[u])) r=u;
            }
            if (r<0) break;
            for (auto& row : core) row.push_back(INF);
            core.emplace_back(i+1, INF);
            core[i][i]=0;
            hubs.push_back(r);
            for (int reverse=0; reverse<2; ++reverse) {
                const auto& adj=reverse?g.in:g.out;
                queue.clear();
                queue.push_back(r);
                depth[r]=0;
                old_hub_on_path[r]=0;
                for (size_t j=0; j<queue.size(); ++j) {
                    int u=queue[j];
                    if (u!=r) {
                        if (rank[u]>=0) {
                            if (reverse) core[rank[u]][i]=depth[u];
                            else core[i][rank[u]]=depth[u];
                        } else if (!old_hub_on_path[u]) {
                            (reverse ? to_hub[u] : from_hub[u]).push_back({i,depth[u]});
                            ++endpoint_labels;
                            cover(u);
                        } else ++omitted;
                    }
                    if (depth[u]>=radius) continue;
                    for (int v : adj[u]) {
                        ++bfs_scans;
                        if (depth[v]>=0) continue;
                        depth[v]=depth[u]+1;
                        old_hub_on_path[v]=old_hub_on_path[u] || rank[u]>=0;
                        queue.push_back(v);
                    }
                }
                for (int v : queue) depth[v]=-1;
            }
            rank[r]=i;
            cover(r);
        }
    }
};

struct Index {
    Layer first, second;
    Graph residual;
    vector<int> tag[2], front[2];
    int stamp=0, lowered=0, added=0;
    explicit Index(Graph g, int radius, int b, int second_limit)
      : first(g.out.size()), second(g.out.size()), residual(std::move(g)) {
        int n=residual.out.size();
        vector<char> covered(n,0);
        first.build(residual,radius,b,covered,{},false);
        residual.remove_hubs(first.rank);
        second.build(residual,radius,second_limit,covered,first.rank,true);
        for (int u : second.hubs) {
            if (first.to_hub[u].empty()) continue;
            for (int v : second.hubs) {
                if (u==v || first.from_hub[v].empty()) continue;
                int& stored=second.core[second.rank[u]][second.rank[v]];
                int candidate=first.through(u,v,-1);
                if (candidate<=radius && candidate<stored) {
                    if (stored==INF) ++added; else ++lowered;
                    stored=candidate;
                }
            }
        }
        residual.remove_hubs(second.rank);
        for (auto& st : tag) st.assign(n,0);
    }
    bool search_residual(int s,int t,int k) {
        ++stamp;
        front[0].assign(1,s); front[1].assign(1,t);
        tag[0][s]=stamp; tag[1][t]=stamp;
        // Alternation gives ceil(k/2) forward and floor(k/2) reverse layers.
        for (int level=0; level<k; ++level) {
            int side=level%2;
            const auto& adj=side?residual.in:residual.out;
            vector<int> next;
            for (int u : front[side]) for (int v : adj[u]) {
                if (tag[1-side][v]==stamp) return true;
                if (tag[side][v]!=stamp) {
                    tag[side][v]=stamp;
                    next.push_back(v);
                }
            }
            if (next.empty()) break;
            front[side].swap(next);
        }
        return false;
    }
    bool query(int s,int t,int k) {
        if (s==t || k==0) return s==t;
        if (first.rank[s]>=0 || first.rank[t]>=0) return first.through(s,t,k)<=k;
        if (second.rank[s]>=0 || second.rank[t]>=0) {
            return second.through(s,t,k)<=k || first.through(s,t,k)<=k;
        }
        if (first.through(s,t,k)<=k || second.through(s,t,k)<=k) return true;
        return search_residual(s,t,k);
    }
};

struct Query { int s,t,k; };
double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now()-start).count();
}
void stats(const char* name,const Layer& l) {
    long long finite=0;
    for (const auto& row : l.core) for (int d : row) finite += d<INF;
    std::cout << "\"" << name << "\":{\"hubs\":" << l.hubs.size()
              << ",\"endpoint_labels\":" << l.endpoint_labels
              << ",\"dense_core_slots\":" << l.hubs.size()*l.hubs.size()
              << ",\"finite_core_distances_including_self\":" << finite
              << ",\"omitted_writes\":" << l.omitted
              << ",\"bfs_edge_scans\":" << l.bfs_scans << "}";
}

int main(int argc,char** argv) {
    if (argc!=8) {
        std::cerr<<"usage: scalable N graph.edges workload.tsv fixed_k_or_general b d2_root_cap answers.txt\n";
        return 2;
    }
    int n=std::stoi(argv[1]), b=std::stoi(argv[5]), d2cap=std::stoi(argv[6]);
    bool general=std::string(argv[4])=="general";
    int radius=general ? n : std::stoi(argv[4]);
    if (n<1 || n>=INF/3 || radius<0 || b<0 || d2cap<0) throw std::invalid_argument("graph size or parameters");
    Graph g(n);
    std::ifstream edges(argv[2]), rows(argv[3]);
    if (!edges || !rows) throw std::runtime_error("unreadable graph or workload");
    int u,v;
    while (edges>>u>>v) g.add(u,v);
    for (auto* adj : {&g.out,&g.in}) for (auto& row : *adj) {
        if (!std::is_sorted(row.begin(),row.end())) std::sort(row.begin(),row.end());
        row.erase(std::unique(row.begin(),row.end()), row.end());
    }
    vector<Query> qs;
    std::string header; std::getline(rows,header);
    int s,t,k,truth_distance;
    while (rows>>s>>t>>k>>truth_distance) {
        if (s<0 || t<0 || s>=n || t>=n || k<0) throw std::invalid_argument("invalid query");
        if (general || k==radius) qs.push_back({s,t,std::min(k,n-1)});
    }
    const auto start=Clock::now();
    Index idx(std::move(g),radius,b,d2cap);
    double build_s=seconds(start);
    long long rem_edges=0;
    for (const auto& row : idx.residual.out) rem_edges+=row.size();
    uint64_t ready=khop_bench::rss_kib();
    auto timing=khop_bench::measure(qs.size(),[&](size_t i){
        return idx.query(qs[i].s,qs[i].t,qs[i].k);
    });
    const auto& answers=timing.answers;
    double query_s=timing.first_ns/1e9;
    std::ofstream output(argv[7]);
    for (char ans : answers) output<<int(ans)<<'\n';
    if (!output) throw std::runtime_error("cannot write answers");
    std::cout << "{\"build_s\":" << build_s << ",\"queries_s\":" << query_s << ",\"n_queries\":" << qs.size()
              << ",\"median_queries_s\":" << timing.median_ns/1e9
              << ",\"query_repeats\":" << timing.repeats << ",\"ready_rss_kib\":" << ready
              << ",\"index_allocated_bytes\":" << idx.first.allocated_bytes()+idx.second.allocated_bytes()
              << ",\"d2_lowered\":" << idx.lowered << ",\"d2_added\":" << idx.added
              << ",\"residual_vertices\":" << n-idx.first.hubs.size()-idx.second.hubs.size()
              << ",\"residual_edges\":" << rem_edges << ",";
    stats("D1",idx.first); std::cout<<","; stats("D2",idx.second); std::cout<<"}\n";
    return 0;
}
