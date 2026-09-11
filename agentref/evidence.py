"""Conservative historical supersession; never infer semantic completion."""


def fold_history(items, key, replaces):
    """Annotate older evidence only when a later matching operation replaces it.

    Input and historical status remain unchanged. Caller decides whether an
    annotation excludes an entry from current continuation candidates.
    """
    result = [dict(item, evidence=list(item.get("evidence", []))) for item in items]
    latest = {}
    for position in range(len(result) - 1, -1, -1):
        item = result[position]
        identity = key(item)
        if identity in latest:
            later = latest[identity]
            item["supersededBy"] = later
            item["evidence"].append(
                f"later matching historical success at entry {later}; not a fresh verification")
        if identity is not None and replaces(item):
            latest.setdefault(identity, position)
    return result


def file_history(operations):
    # Only an evidenced full write establishes replacement; a generic Edit or
    # failed write must not erase an earlier known state. Paths match exactly.
    return fold_history(operations, lambda x: (x["path"], x["cwd"]) if isinstance(x.get("cwd"), str) and x["cwd"] else None,
                        lambda x: x["status"] == "COMPLETED" and bool(x.get("expectedSha256")))


def command_history(commands):
    # Identical text in different/unknown directories is not a proven retry.
    return fold_history(commands,
                        lambda x: (x["task"], x["cwd"]) if isinstance(x.get("cwd"), str) and x["cwd"] else None,
                        lambda x: x["status"] == "COMPLETED")


def continuation_candidates(work, limit=12):
    candidates = [x for x in work if x["status"] != "COMPLETED"
                  and "supersededBy" not in x and x.get("planStatus") != "completed"]
    # Explicit remaining plans precede opaque historical calls. Within a priority
    # prefer newer evidence, without claiming a dependency graph.
    priority = {"NOT_STARTED": 0, "PARTIAL": 1, "FAILED": 2, "UNCERTAIN": 3}
    ordered = sorted(enumerate(candidates), key=lambda pair: (priority[pair[1]["status"]], -pair[0]))
    tasks = list(dict.fromkeys(item["task"] for _, item in ordered))
    return {"policy": "Verify current state and dependency order. Explicit pending plans and recent unresolved evidence are prioritized; ordering is not a proven dependency graph. Superseded history is retained separately. Agent-reported completed plans still need verification.",
            "candidates": tasks[:limit], "omittedCandidates": max(0, len(tasks) - limit)}
