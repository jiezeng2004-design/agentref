"""Conservative historical supersession; never infer semantic completion."""
import heapq
from operator import itemgetter

_CANDIDATE_PRIORITY = {"NOT_STARTED": 0, "PARTIAL": 1, "FAILED": 2, "UNCERTAIN": 3}


def fold_history(items, key, replaces, copy_evidence=True):
    """Annotate older evidence only when a later matching operation replaces it.

    Input and historical status remain unchanged. Caller decides whether an
    annotation excludes an entry from current continuation candidates. Internal
    read-only rendering may set copy_evidence=False to share evidence lists for
    unannotated entries; superseded entries always get a private list before append.
    """
    result = []
    for item in items:
        copied = dict(item)
        if copy_evidence or "evidence" not in copied:
            copied["evidence"] = list(item.get("evidence", []))
        result.append(copied)
    latest = {}
    for position in range(len(result) - 1, -1, -1):
        item = result[position]
        identity = key(item)
        if identity in latest:
            later = latest[identity]
            item["supersededBy"] = later
            if not copy_evidence:
                item["evidence"] = list(item.get("evidence", []))
            item["evidence"].append(
                f"later matching historical success at entry {later}; not a fresh verification")
        if identity is not None and replaces(item):
            latest.setdefault(identity, position)
    return result


def file_history(operations, copy_evidence=True):
    # Only an evidenced full write establishes replacement; a generic Edit or
    # failed write must not erase an earlier known state. Paths match exactly.
    return fold_history(operations, lambda x: (x["path"], x["cwd"]) if isinstance(x.get("cwd"), str) and x["cwd"] else None,
                        lambda x: x["status"] == "COMPLETED" and bool(x.get("expectedSha256")),
                        copy_evidence=copy_evidence)


def command_history(commands, copy_evidence=True):
    # Identical text in different/unknown directories is not a proven retry.
    return fold_history(commands,
                        lambda x: (x["task"], x["cwd"]) if isinstance(x.get("cwd"), str) and x["cwd"] else None,
                        lambda x: x["status"] == "COMPLETED", copy_evidence=copy_evidence)


def continuation_candidates(work, limit=12):
    # Explicit remaining plans precede opaque historical calls. Within a priority
    # prefer newer evidence, without claiming a dependency graph.
    try:
        rank_scale = len(work) + 1
    except TypeError:
        rank_scale = None
    # Keep only each task's best rank. This is equivalent to sorting every
    # candidate then deduplicating, but avoids an O(n log n) sort and the extra
    # candidate/sorted lists for long sessions.
    best = {}
    candidate_position = 0
    for item in work:
        if (item["status"] == "COMPLETED" or "supersededBy" in item
                or item.get("planStatus") == "completed"):
            continue
        rank = (_CANDIDATE_PRIORITY[item["status"]] * rank_scale - candidate_position
                if rank_scale is not None
                else (_CANDIDATE_PRIORITY[item["status"]], -candidate_position))
        candidate_position += 1
        task = item["task"]
        previous = best.get(task)
        if previous is None or rank < previous:
            best[task] = rank
    take = max(0, len(best) + limit) if limit < 0 else limit
    tasks = [task for task, _ in heapq.nsmallest(take, best.items(), key=itemgetter(1))]
    return {"policy": "Verify current state and dependency order. Explicit pending plans and recent unresolved evidence are prioritized; ordering is not a proven dependency graph. Superseded history is retained separately. Agent-reported completed plans still need verification.",
            "candidates": tasks, "omittedCandidates": max(0, len(best) - limit)}
