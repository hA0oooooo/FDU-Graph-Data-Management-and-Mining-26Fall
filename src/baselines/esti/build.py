"""Build the fixed upstream ESTI release with a per-query answer stream."""
import hashlib
import subprocess
from pathlib import Path
from urllib.request import urlretrieve

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[2] / "cache/esti"
INCLUDE = HERE.parents[1]
BINARY = BUILD / "esti-batch"
REV = "d893a28de9bf8f407ed24ebefc973f973be1e923"
ARCHIVE_SHA = "02ac5b59e915fdcfde8dd7c30bcce5bcfbf92d4e72ab307aff2786684bf122f3"
URL = f"https://codeload.github.com/YZ-Cai/ESTI/tar.gz/{REV}"


def build():
    BUILD.mkdir(parents=True, exist_ok=True)
    archive = BUILD / "upstream.tar.gz"
    if not archive.exists():
        partial = BUILD / "upstream.part"
        urlretrieve(URL, partial)
        partial.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA:
        raise ValueError(f"ESTI archive SHA-256 mismatch: {archive}")
    subprocess.run(["tar", "xzf", archive, "-C", BUILD], check=True)
    src = BUILD / f"ESTI-{REV}" / "ESTI"
    original = (src / "ESTI.cpp").read_text()
    # Keep the author construction and ESTI_query kernel intact.
    include='#include "data_structure.h"'
    if original.count(include)!=1:
        raise ValueError("unexpected ESTI includes")
    original=original.replace(include,'#include "benchmark_metrics.hpp"\n'+include)
    begin=original.index("\tbool result;")
    stop=original.index("double query_time =  endTime();",begin)+len("double query_time =  endTime();")
    observation=r"""
    tri_stk = new tri[maxn];
    printf("ESTI Querying...\n");
    auto ready=khop_bench::rss_kib();
    auto timing=khop_bench::measure(queryNumber,[&](size_t i) {
        int& start=qlist[reversed][i];
        int& end=qlist[!reversed][i];
        K=qlist[3][i];
        return ESTI_query(start,end,K);
    });
    double query_time=timing.first_ns/1e6;
    printf("median query time: %.6lf ms\n",timing.median_ns/1e6);
    printf("query repeats: %u\n",timing.repeats);
    printf("ready rss: %llu KiB\n",(unsigned long long)ready);
    unsigned long long allocated=(N+1ull)*sizeof(ESTI_index)+sizeof(EST_node)+sizeof(link2root);
    for(int i=0;i<N;++i)allocated+=(unsigned long long)in_degree(i)*sizeof(EST_node);
    for(int i=0;i<=N;++i)
        allocated+=(unsigned long long)ESTI[i].real_and_virtual_nodes[0].children_cnt*sizeof(EST_node*);
    printf("allocated index bytes: %llu\n",allocated);
    std::ofstream output("answers.txt");
    for(auto answer:timing.answers)output<<int(answer)<<'\n';
"""
    original=original[:begin]+observation+original[stop:]
    observed=src/"ESTI-batch-observed.cpp"
    observed.write_text(original)
    subprocess.run(["g++","-std=c++11","-O3","-m64","-I",INCLUDE,observed,"-o",BINARY],check=True)


def ensure_built():
    sources=(Path(__file__),INCLUDE/"benchmark_metrics.hpp")
    if not BINARY.exists() or BINARY.stat().st_mtime_ns<max(p.stat().st_mtime_ns for p in sources):
        build()


if __name__ == "__main__":
    build()
