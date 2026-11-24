#pragma once
#include "graph.hpp"
#include <queue>

namespace khop {
// A topological violation between distinct SCCs rules out every original path.
struct Topology {
    std::vector<Node> component, first, second;
    explicit Topology(const Graph& g):component(g.n,g.n) {
        std::vector<bool> seen(g.n);
        std::vector<Node> finish;
        const auto& out=g.side[1];
        for (Node s=0;s<g.n;++s) if (!seen[s]) {
            std::vector<std::pair<Node,uint32_t>> stack{{s,out.offsets[s]}};
            seen[s]=true;
            while (!stack.empty()) {
                auto& [v,j]=stack.back();
                if (j==out.offsets[v+1]) {finish.push_back(v);stack.pop_back();continue;}
                Node w=out.neighbors[j++];
                if (!seen[w]) {seen[w]=true;stack.emplace_back(w,out.offsets[w]);}
            }
        }
        Node count=0;
        const auto& in=g.side[0];
        for (auto it=finish.rbegin();it!=finish.rend();++it) if (component[*it]==g.n) {
            std::vector<Node> stack{*it};component[*it]=count;
            while (!stack.empty()) {
                Node v=stack.back();stack.pop_back();
                for(auto j=in.offsets[v];j<in.offsets[v+1];++j) {
                    Node w=in.neighbors[j];
                    if(component[w]==g.n) {component[w]=count;stack.push_back(w);}
                }
            }
            ++count;
        }
        std::vector<std::vector<Node>> dag(count);
        for(Node u=0;u<g.n;++u) for(auto j=out.offsets[u];j<out.offsets[u+1];++j)
            if(component[u]!=component[out.neighbors[j]]) dag[component[u]].push_back(component[out.neighbors[j]]);
        std::vector<Node> indegree(count);
        for(auto& row:dag) {
            std::sort(row.begin(),row.end());row.erase(std::unique(row.begin(),row.end()),row.end());
            for(auto v:row) ++indegree[v];
        }
        auto order=[&](bool ascending) {
            auto comp=[ascending](Node a,Node b){return ascending?a>b:a<b;};
            std::priority_queue<Node,std::vector<Node>,decltype(comp)> ready(comp);
            auto deg=indegree;
            for(Node v=0;v<count;++v) if(!deg[v]) ready.push(v);
            std::vector<Node> rank(count);
            for(Node i=0;!ready.empty();++i) {
                Node v=ready.top();ready.pop();rank[v]=i;
                for(Node w:dag[v]) if(!--deg[w]) ready.push(w);
            }
            return rank;
        };
        first=order(true);second=order(false);
    }
    char witness(const Graph&,const Query& q) const {
        Node a=component[q.s], b=component[q.t];
        return first[a]>first[b] || second[a]>second[b]?'L':0;
    }
};

// Persist only cover vertices in the forest. An arc can stand for two real edges
// via an outside vertex; the offset is retained when accumulating depth.
struct CoverTree {
    std::vector<int> id;
    std::vector<Node> pre,post,depth;
    explicit CoverTree(const Graph& g):id(g.n,-1) {
        const auto& out=g.side[1];
        int size=0;
        for(Node u=0;u<g.n;++u) for(auto j=out.offsets[u];j<out.offsets[u+1];++j) {
            Node v=out.neighbors[j];
            if(id[u]<0 && id[v]<0) {id[u]=size++;if(v!=u)id[v]=size++;}
        }
        std::vector<Node> roots;
        for(Node u=0;u<g.n;++u) if(id[u]>=0) roots.push_back(u);
        auto degree=[&](Node u){return Count(out.degree(u))+g.side[0].degree(u);};
        std::sort(roots.begin(),roots.end(),[&](Node a,Node b){return degree(a)!=degree(b)?degree(a)>degree(b):a<b;});
        std::vector<bool> seen(g.n);
        std::vector<std::vector<int>> children(size);
        std::vector<int> forest_roots;
        pre.resize(size);post.resize(size);depth.resize(size);
        for(auto root:roots) if(!seen[root]) {
            seen[root]=true;forest_roots.push_back(id[root]);
            std::vector<Node> queue{root};
            for(size_t pos=0;pos<queue.size();++pos) {
                Node u=queue[pos];
                auto visit=[&](Node v,int weight) {
                    if(seen[v])return;
                    seen[v]=true;queue.push_back(v);children[id[u]].push_back(id[v]);
                    depth[id[v]]=depth[id[u]]+weight;
                };
                for(auto j=out.offsets[u];j<out.offsets[u+1];++j) {
                    Node v=out.neighbors[j];
                    if(id[v]>=0) visit(v,1);
                    else if(!seen[v]) {
                        seen[v]=true;
                        for(auto t=out.offsets[v];t<out.offsets[v+1];++t) visit(out.neighbors[t],2);
                    }
                }
            }
        }
        Node clock=0;
        for(auto root:forest_roots) {
            std::vector<std::pair<int,size_t>> stack{{root,0}};pre[root]=clock++;
            while(!stack.empty()) {
                auto& [u,j]=stack.back();
                if(j==children[u].size()) {post[u]=clock;stack.pop_back();continue;}
                int v=children[u][j++]; pre[v]=clock++;stack.emplace_back(v,0);
            }
        }
    }
    char witness(const Graph& g,const Query& q) const {
        const auto& out=g.side[1];const auto& in=g.side[0];
        bool enter=id[q.s]<0, leave=id[q.t]<0;
        auto ns=enter?out.degree(q.s):1, nt=leave?in.degree(q.t):1;
        int k=q.k-enter-leave;
        if(k<0 || Count(ns)*nt>64) return 0;
        for(Node i=0;i<ns;++i) for(Node j=0;j<nt;++j) {
            auto a=id[enter?out.neighbors[out.offsets[q.s]+i]:q.s];
            auto b=id[leave?in.neighbors[in.offsets[q.t]+j]:q.t];
            if(pre[a]<=pre[b] && pre[b]<post[a] && depth[b]-depth[a]<=unsigned(k)) return 'U';
        }
        return 0;
    }
};
}
