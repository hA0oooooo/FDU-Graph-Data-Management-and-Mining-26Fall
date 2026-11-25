"""Compile the observed ESTI source with a larger edge-array capacity."""
from pathlib import Path
import shutil
import subprocess
import tempfile

from .build import BUILD, REV, build


def expanded(edge_slots):
    original = BUILD / ("ESTI-" + REV)
    if not (original / "ESTI/ESTI-observed.cpp").exists():
        build()
    dest = BUILD / ("esti-edges-" + str(edge_slots))
    with tempfile.TemporaryDirectory(dir=BUILD) as folder:
        root = Path(folder)
        shutil.copytree(original / "ESTI", root / "ESTI")
        header = (original / "common.h").read_text()
        definition = "#define maxm 60000000"
        if header.count(definition) != 1:
            raise ValueError("upstream edge-capacity definition differs")
        (root / "common.h").write_text(header.replace(definition, f"#define maxm {edge_slots}"))
        subprocess.run(["g++", "-std=c++11", "-O3", "-m64", root / "ESTI/ESTI-observed.cpp",
                        "-o", dest], check=True)
    return dest
