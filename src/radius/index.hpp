#pragma once
#include "graph.hpp"
#include <tuple>

namespace khop {
constexpr int max_radius=6;
struct Profile {
    std::vector<uint8_t> dist;
    std::array<Count,max_radius+1> entries{}, scans{};
};

inline Profile explore(const Adjacency& adj,Node root,int limit) {
    Profile p;
    p.dist.assign(adj.offsets.size()-1,255);
    p.dist[root]=0; p.entries[0]=1;
    std::vector<Node> current{root},next;
    for (int h=1;h<=limit;++h) {
        next.clear();
        for (auto u:current) {
            p.scans[h]+=adj.degree(u);
            for (auto j=adj.offsets[u];j<adj.offsets[u+1];++j) {
                Node v=adj.neighbors[j];
                if (p.dist[v]==255) { p.dist[v]=h; next.push_back(v); }
            }
        }
        p.entries[h]=p.entries[h-1]+next.size();
        current.swap(next);
    }
    return p;
}

inline std::vector<Node> landmarks(const Graph& g) {
    std::vector<Node> ids(g.n);
    std::iota(ids.begin(),ids.end(),0);
    auto degree=[&](Node v){return Count(g.side[0].degree(v))+g.side[1].degree(v);};
    auto end=ids.begin()+std::min<size_t>(12,ids.size());
    std::partial_sort(ids.begin(),end,ids.end(),[&](Node a,Node b) {
        return degree(a)!=degree(b)?degree(a)>degree(b):a<b;
    });
    ids.erase(end,ids.end());
    return ids;
}

using Config=std::vector<int>; // paired incoming/outgoing, in root order
using Profiles=std::vector<Profile>;
inline Count labels(const Profiles& p,const Config& h) {
    Count n=0;
    for (size_t i=0;i<h.size();++i) n+=p[i].entries[h[i]];
    return n;
}
inline char certificate(int is,int it,int os,int ot,int hi,int ho,int k) {
    if (is<=hi && ot<=ho && is+ot<=k) return 'U';
    if (is-it>k || ot-os>k) return 'L';
    return 0;
}

// Structural comparison uses only completed layer sizes and frontier edge counts.
inline Config structural(const Profiles& p,Count cap) {
    Config h(p.size());
    Count count=h.size();
    std::vector<bool> retired(p.size());
    for (;;) {
        int best=-1;
        for (int i=0;i<int(h.size());++i) if (!retired[i] && h[i]<max_radius) {
            if (best<0 || std::tie(h[i],p[i].scans[h[i]+1],i) <
                          std::tie(h[best],p[best].scans[h[best]+1],best)) best=i;
        }
        if (best<0) break;
        Count delta=p[best].entries[h[best]+1]-p[best].entries[h[best]];
        if (count+delta>cap) { retired[best]=true; continue; }
        count+=delta; ++h[best];
        if (h[best]<max_radius && !p[best].scans[h[best]+1]) h[best]=max_radius;
    }
    return h;
}

inline bool profile_hit(const Profiles& p,int side,int a,int b,const Query& q) {
    auto in=[&](Node v){return std::min<int>(a+1,p[side].dist[v]);};
    auto out=[&](Node v){return std::min<int>(b+1,p[side+1].dist[v]);};
    return certificate(in(q.s),in(q.t),out(q.s),out(q.t),a,b,q.k);
}

inline Config allocate(const Profiles& p,Count cap,const std::vector<Query>& train,
                       const std::vector<unsigned>& weights) {
    Config h(p.size());
    Count count=h.size();
    std::vector<bool> covered(train.size());
    for (;;) {
        double best_score=0;
        int chosen=-1,hin=0,hout=0;
        Count cost=0;
        for (int i=0;i<int(h.size());i+=2) {
            for (int a=h[i];a<=max_radius;++a) for (int b=h[i+1];b<=max_radius;++b) {
                if (a==h[i] && b==h[i+1]) continue;
                Count delta=p[i].entries[a]-p[i].entries[h[i]]
                           +p[i+1].entries[b]-p[i+1].entries[h[i+1]];
                if (count+delta>cap) continue;
                int64_t gain=0;
                for (size_t q=0;q<train.size();++q) {
                    if (covered[q] || !weights[q]) continue;
                    if (profile_hit(p,i,a,b,train[q])) gain+=weights[q];
                    if (h[i]==0 && h[i+1]==0) gain-=4;
                }
                double score=double(gain)/std::max<Count>(delta,1);
                if (score>best_score) {
                    best_score=score; chosen=i; hin=a; hout=b; cost=delta;
                }
            }
        }
        if (chosen<0) break;
        h[chosen]=hin; h[chosen+1]=hout; count+=cost;
        for (size_t q=0;q<train.size();++q)
            if (!covered[q] && weights[q]) covered[q]=profile_hit(p,chosen,hin,hout,train[q]);
    }
    return h;
}

struct Table {
    int h;
    Node root;
    std::vector<uint8_t> values;
    std::vector<Node> ids;
    bool dense=false;
    Table(const Profile& p,Node r,int depth):h(depth),root(r) {
        if (!h) return; // implicit root
        dense=p.dist.size()<=5*p.entries[h];
        if (dense) {
            values=p.dist;
            for (auto& x:values) x=std::min<int>(x,h+1);
        } else {
            ids.reserve(p.entries[h]); values.reserve(p.entries[h]);
            for (Node v=0;v<p.dist.size();++v) if (p.dist[v]<=h) {
                ids.push_back(v); values.push_back(p.dist[v]);
            }
        }
    }
    int at(Node v) const {
        if (!h) return v==root?0:1;
        if (dense) return values[v];
        auto it=std::lower_bound(ids.begin(),ids.end(),v);
        return it==ids.end() || *it!=v ? h+1:values[it-ids.begin()];
    }
};

struct Index {
    std::vector<std::pair<Table,Table>> active;
    Count bytes() const {
        Count sum=active.capacity()*sizeof(active[0]);
        for (auto& [a,b]:active) for (auto t:{&a,&b})
            sum+=4*t->ids.capacity()+t->values.capacity();
        return sum;
    }
    Index(const Profiles& p,const std::vector<Node>& roots,const Config& h) {
        for (size_t i=0;i<roots.size();++i) if (h[2*i] || h[2*i+1])
            active.emplace_back(Table(p[2*i],roots[i],h[2*i]),Table(p[2*i+1],roots[i],h[2*i+1]));
    }
    Index(const Graph& g,const std::vector<Node>& roots,const Config& h) {
        for (size_t i=0;i<roots.size();++i) if (h[2*i] || h[2*i+1]) {
            auto table=[&](int side) {
                int depth=h[2*i+side];
                return Table(depth?explore(g.side[side],roots[i],depth):Profile{},roots[i],depth);
            };
            active.emplace_back(table(0),table(1));
        }
    }
    Answer query(const Graph& g,Search& search,const Query& q) const {
        if (q.s==q.t || !q.k || !g.side[1].degree(q.s) || !g.side[0].degree(q.t))
            return {q.s==q.t,'T',0};
        for (const auto& [in,out]:active) {
            auto c=certificate(in.at(q.s),in.at(q.t),out.at(q.s),out.at(q.t),in.h,out.h,q.k);
            if (c) return {c=='U',c,0};
        }
        return search.run(q);
    }
};
}
