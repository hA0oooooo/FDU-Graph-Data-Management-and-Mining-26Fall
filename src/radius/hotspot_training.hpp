#pragma once
#include "hotspot.hpp"
#include "query_io.hpp"
#include <set>

namespace khop {
using Bins=std::array<Count,max_radius+1>;

struct RootTrace : PlainSearch {
    std::vector<Count> edges;
    explicit RootTrace(Node n):edges(n) {}
    void scanned(Node u,int,int j,int,Count a) { if(j) edges[u]+=a; }
};
std::vector<Node> choose_roots(const Graph& g,Search& search,const std::vector<Query>& train) {
    RootTrace trace(g.n);
    for (const Query& q:train) check(q,search.guided(q,trace));
    std::vector<Node> ids(g.n);
    std::iota(ids.begin(),ids.end(),0);
    ids.erase(std::remove_if(ids.begin(),ids.end(),[&](Node u){return !trace.edges[u];}),ids.end());
    auto end=ids.begin()+std::min<size_t>(12,ids.size());
    std::partial_sort(ids.begin(),end,ids.end(),[&](Node a,Node b){
        return trace.edges[a]!=trace.edges[b]?trace.edges[a]>trace.edges[b]:a<b;
    });
    ids.erase(end,ids.end());
    std::sort(ids.begin(),ids.end());
    return ids;
}

struct Histogram : PlainSearch {
    const std::vector<Node>& roots;
    std::vector<Bins> scans,visits;
    std::vector<std::array<std::set<Node>,max_radius+1>> sources;
    Node source=0;
    Count total=0;
    explicit Histogram(const std::vector<Node>& ids):roots(ids),scans(2*ids.size()),
        visits(scans.size()),sources(scans.size()) {}
    void scanned(Node u,int dir,int j,int r,Count a) {
        total+=a;
        if (!j) return;
        auto it=std::lower_bound(roots.begin(),roots.end(),u);
        if (it==roots.end() || *it!=u) return;
        size_t p=2*(it-roots.begin())+dir;
        scans[p].at(r)+=a;
        ++visits[p].at(r);
        sources[p].at(r).insert(source);
    }
};
Histogram histogram(Search& search,const std::vector<Query>& qs,const std::vector<Node>& roots) {
    Histogram hist(roots);
    for (const Query& q:qs) {
        hist.source=q.s;
        Count before=hist.total;
        auto a=search.guided(q,hist);
        check(q,a);
        if (hist.total-before!=a.scans) throw std::runtime_error("edge accounting mismatch");
    }
    return hist;
}
Profiles profiles(const Graph& g,const std::vector<Node>& roots,const Config& depths) {
    Profiles result;
    for (size_t i=0;i<depths.size();++i)
        result.push_back(depths[i]?explore(g.side[i%2],roots[i/2],depths[i]):Profile{});
    return result;
}
std::vector<Config> proposals(const Graph& g,const Profiles& p,const Histogram& hist,int uniform,Count cap,const Config& limits) {
    Config cfg(p.size(),0);
    std::vector<Config> result{cfg};
    Count previous=0;
    for (;;) {
        double best=0;
        Count best_bytes=0;
        size_t chosen=0; int depth=0;
        for (size_t i=0;i<p.size();++i) {
            int h=cfg[i];
            Count gain=0;
            for (int j=h+1;j<=limits[i];++j) {
                gain+=hist.scans[i][j];
                if (!gain || (uniform && j!=uniform)) continue;
                cfg[i]=j;
                Count bytes=HotIndex::estimate(p,cfg,g.n);
                cfg[i]=h;
                if (bytes>cap) continue;
                double score=double(gain)/std::max<Count>(1,bytes>previous?bytes-previous:0);
                if (score>best || (score==best && bytes<best_bytes)) {
                    best=score; best_bytes=bytes; chosen=i; depth=j;
                }
            }
        }
        if (!best) break;
        cfg[chosen]=depth; previous=best_bytes;
        if (result.size()==1) result.push_back(cfg);
    }
    if (result.back()!=cfg) result.push_back(cfg);
    return result;
}

// Only complete positive-depth profiles may be used by the selector.
Config probe_limits(const Histogram& hist, const std::string& policy, int k) {
    int cap=std::min(max_radius,k-1);
    Config limits(hist.scans.size(),max_radius);
    if (policy=="full") return limits;
    if (policy!="global" && policy!="demand") throw std::invalid_argument("unknown profile policy");
    for (size_t i=0;i<limits.size();++i) {
        int demand=0;
        for (int h=1;h<=cap;++h) if (hist.scans[i][h]) demand=h;
        limits[i]=demand && policy=="global"?cap:demand;
    }
    return limits;
}

std::vector<Config> candidates_for(const Graph& g,const Profiles& p,const Histogram& hist,
                                   const Config& limits,bool uniform,int upper,Count cap) {
    std::vector<Config> candidates;
    for (int h=uniform?1:0;h<=(uniform?upper:0);++h)
        for(auto& cfg:proposals(g,p,hist,h,cap,limits))
            if (std::find(candidates.begin(),candidates.end(),cfg)==candidates.end()) candidates.push_back(cfg);
    return candidates;
}

}
