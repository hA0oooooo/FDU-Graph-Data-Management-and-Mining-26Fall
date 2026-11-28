#pragma once
#include "index.hpp"

namespace khop {
struct HotIndex {
    using Pair = std::pair<Table, Table>;
    std::vector<Pair> tables;
    std::vector<uint64_t> membership;

    static Count estimate(const Profiles& profiles, const Config& cfg, Node n) {
        Count total=0;
        for (size_t i=0;i<cfg.size();i+=2) {
            if (!cfg[i] && !cfg[i+1]) continue;
            total+=sizeof(Pair);
            for (size_t side=i;side<=i+1;++side) if (cfg[side])
                total+=std::min<Count>(n,5*profiles[side].entries[cfg[side]]);
        }
        return total ? total+sizeof(uint64_t)*((Count(n)+63)/64) : 0;
    }

    HotIndex(const Profiles& profiles,const Config& cfg,const std::vector<Node>& roots,Node n) {
        size_t active=0;
        for (size_t i=0;i<roots.size();++i) active+=(cfg[2*i] || cfg[2*i+1]);
        if (!active) return;
        membership.assign((Count(n)+63)/64,0);
        tables.reserve(active);
        for (size_t i=0;i<roots.size();++i) if (cfg[2*i] || cfg[2*i+1]) {
            Node root=roots[i];
            membership[root/64]|=uint64_t(1)<<(root%64);
            tables.emplace_back(Table(profiles[2*i],root,cfg[2*i]),Table(profiles[2*i+1],root,cfg[2*i+1]));
        }
        if (bytes()!=estimate(profiles,cfg,n)) throw std::logic_error("index allocation estimate differs");
    }

    Count bytes() const {
        Count n=membership.capacity()*sizeof(uint64_t)+tables.capacity()*sizeof(Pair);
        for (const auto& [in,out]:tables) for (const Table* t:{&in,&out})
            n+=t->ids.capacity()*sizeof(Node)+t->values.capacity();
        return n;
    }

    int decide(Node u,int dir,int,int remaining,Node target) const {
        if (membership.empty() || !(membership[u/64] & (uint64_t(1)<<(u%64)))) return 0;
        const auto it=std::lower_bound(tables.begin(),tables.end(),u,
            [](const Pair& p,Node v){return p.first.root<v;});
        const Table& table=dir?it->second:it->first;
        if (!table.h) return 0;
        int z=table.at(target);
        if (z<=table.h && z<=remaining) return 1;
        return remaining<=table.h ? -1 : 0;
    }
    void scanned(Node,int,int,int,Count) const {}

    Answer query(Search& search,const Query& q) const {
        return tables.empty()?search.run(q):search.guided(q,*this);
    }
};
}
