"""Measure structure from every frozen directed graph."""
import json
import subprocess
from radius.run import ROOT,compile_tool,digest


if __name__=="__main__":
    data=ROOT/"dataset"
    original=json.loads((data/"manifest.json").read_text())
    graphs=original|json.loads((data/"catalogue.json").read_text())|json.loads((data/"synthetic.json").read_text())
    binary=compile_tool("graph_stats")
    path=data/"graph_stats.tsv"
    tmp=path.with_suffix(".part")
    with tmp.open("w") as f:
        f.write("graph\tnodes\tedges\tloops\tsccs\tlargest_scc\tzero_out\tzero_in\tmedian_outdegree\tmax_outdegree\tmax_indegree\treciprocal_arcs\tmean_outdegree\tdirected_nonloop_density\n")
        f.flush()
        for name,spec in sorted(graphs.items()):
            edges=data/"prepared"/f"{name}.edges"
            frozen=original[name] if name in original else json.loads((data/"frozen"/f"{name}.json").read_text())
            if digest(edges)!=frozen["edges_sha256"]:
                raise ValueError(f"{name}: graph differs from freeze")
            subprocess.run([binary,name,str(spec["nodes"]),edges],stdout=f,check=True)
    tmp.replace(path)
