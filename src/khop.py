"""Exact bounded reachability on a directed graph with dense integer vertex IDs."""

from dataclasses import dataclass


def bfs(out, inc, s, t, k):
    """Forward BFS. Count each adjacency entry actually inspected."""
    if k < 0:
        raise ValueError("negative hop bound")
    if s == t or k == 0:
        return s == t, 0
    frontier = [s]
    seen = {s}
    scans = 0
    for _ in range(k):
        following = []
        for u in frontier:
            for v in out[u]:
                scans += 1
                if v == t:
                    return True, scans
                if v not in seen:
                    seen.add(v)
                    following.append(v)
        if not following:
            break
        frontier = following
    return False, scans


def bibfs(out, inc, s, t, k):
    """Expand a complete layer on the side with fewer incident edges."""
    if k < 0:
        raise ValueError("negative hop bound")
    if s == t or k == 0:
        return s == t, 0
    directions = (out, inc)
    seen = ({s}, {t})
    frontiers = [[s], [t]]
    work = [len(out[s]), len(inc[t])]
    scans = 0
    # After i layers the two radii sum to i. A path of length <= i
    # would already have intersected, regardless of the order of expansion.
    for _ in range(k):
        side = int(work[1] < work[0])
        if work[side] == 0:
            break
        adj = directions[side]
        own, other = seen[side], seen[1 - side]
        following = []
        next_work = 0
        for u in frontiers[side]:
            for v in adj[u]:
                scans += 1
                if v in other:
                    return True, scans
                if v not in own:
                    own.add(v)
                    following.append(v)
                    next_work += len(adj[v])
        frontiers[side] = following
        work[side] = next_work
    return False, scans


def choose_landmarks(out, inc, count):
    """Rank by total directed degree; vertex ID breaks a tie."""
    if count < 0:
        raise ValueError("negative landmark count")
    return sorted(range(len(out)), key=lambda v: (-len(out[v]) - len(inc[v]), v))[:count]


@dataclass
class _Ball:
    distance: dict
    frontier: list
    work: int
    radius: int = 0

    def advance(self, adj, limit, free):
        """Commit one whole BFS layer; abandon it upon exceeding remaining entries."""
        new_vertices = {}
        scans = 0
        for u in self.frontier:
            for v in adj[u]:
                scans += 1
                if v not in self.distance and v not in new_vertices:
                    if len(new_vertices) == free:
                        return False, 0, scans
                    new_vertices[v] = self.radius + 1
        self.distance.update(new_vertices)
        self.frontier = list(new_vertices)
        self.work = sum(len(adj[v]) for v in self.frontier)
        # A frontier with no edges certifies all remaining layers at zero extra cost.
        self.radius = self.radius + 1 if self.work else limit
        return True, len(new_vertices), scans


class Index:
    def __init__(self, out, inc, balls, entries, build_scans):
        self.out, self.inc = out, inc
        self.entries = entries
        self.build_scans = build_scans
        self.radii = []
        self._labels = []
        for inward, outward in zip(balls[::2], balls[1::2]):
            self.radii.append((inward.radius, outward.radius))
            self._labels.append((inward.distance, outward.distance,
                                 inward.radius + 1, outward.radius + 1))
        # With only roots stored, the lower bound is <=1 and any two-leg
        # witness has identical endpoints. Both trivial cases are handled first.
        self._query_labels = self._labels if any(a or b for a, b in self.radii) else ()

    def query(self, s, t, k):
        if k < 0:
            raise ValueError("negative hop bound")
        if s == t or k == 0:
            return s == t, "trivial", 0
        for inward, outward, in_clip, out_clip in self._query_labels:
            to_root = inward.get(s, in_clip)
            from_root = outward.get(t, out_clip)
            if to_root < in_clip and from_root < out_clip and to_root + from_root <= k:
                return True, "upper", 0
            # Clipped directed distances still obey a unit one-sided Lipschitz bound.
            if (from_root - outward.get(s, out_clip) > k or
                    to_root - inward.get(t, in_clip) > k):
                return False, "lower", 0
        answer, scans = bibfs(self.out, self.inc, s, t, k)
        return answer, "fallback", scans


class IndexBudgetError(ValueError):
    """An infeasible configuration, including the edge scans spent finding out."""

    def __init__(self, build_scans):
        super().__init__("index does not fit the label-entry budget")
        self.build_scans = build_scans


def build_index(out, inc, landmarks, mode, h, cap):
    """Build complete incoming/outgoing balls, with each root stored twice.

    Uniform requires every direction to reach h. Adaptive gives shallower
    directions first access to the budget. At a given depth it prefers the
    frontier with fewer edges to scan. A layer that would not fit is discarded,
    its scans are charged, and its direction retires as free space only shrinks.
    Neither policy reads queries. radii has (in_radius, out_radius) per root.
    """
    if mode not in ("uniform", "adaptive") or h < 0 or cap < 0:
        raise ValueError("invalid index mode, radius or budget")
    entries = 2 * len(landmarks)
    if entries > cap:
        raise IndexBudgetError(0)
    directions = (inc, out)
    balls = [_Ball({v: 0}, [v], len(adj[v])) for v in landmarks for adj in directions]
    active = [i for i in range(len(balls)) if h]
    build_scans = 0
    while active:
        if mode == "adaptive":
            i = min(active, key=lambda j: (balls[j].radius, balls[j].work, j))
        else:
            i = active[0]
        ball = balls[i]
        complete, new_entries, scans = ball.advance(directions[i % 2], h, cap - entries)
        entries += new_entries
        build_scans += scans
        if not complete and mode == "uniform":
            raise IndexBudgetError(build_scans)
        if not complete or ball.radius == h:
            active.remove(i)
    return Index(out, inc, balls, entries, build_scans)
