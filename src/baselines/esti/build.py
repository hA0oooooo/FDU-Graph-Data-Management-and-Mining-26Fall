"""Build the fixed upstream ESTI release with a per-query answer stream."""
import hashlib
import subprocess
from pathlib import Path
from urllib.request import urlretrieve

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[2] / "cache/esti"
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
    # Keep the author kernel and construction intact. Emit the buffered answers
    # only once the original query timer has stopped.
    edits = {
        "bool result;": "std::vector<char> answers(queryNumber);",
        "result = ESTI_query(start, end, K);":
            "answers[i] = ESTI_query(start, end, K) ? '1' : '0';",
        "double query_time =  endTime();":
            'double query_time = endTime();\n'
            '    std::ofstream output("answers.txt");\n'
            "    for (char answer : answers) output << answer << '\\n';",
    }
    for old, new in edits.items():
        if original.count(old) != 1:
            raise ValueError(f"Unexpected upstream source around {old!r}")
        original = original.replace(old, new)
    observed = src / "ESTI-observed.cpp"
    observed.write_text(original)
    subprocess.run(["g++", "-std=c++11", "-O3", "-m64", observed,
                    "-o", BUILD / "esti"], check=True)


if __name__ == "__main__":
    build()
