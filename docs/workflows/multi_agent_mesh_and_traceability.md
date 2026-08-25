# Workflow: Multi-Agent Mesh Coordination & Traceability

## Recovery evidence

Coordination recovery combines bounded replay, failure, and mined mistake evidence. Each is read-only context for manual reconciliation; none changes ownership, merges a branch, or executes recorded work.

## Coordination receipt workflow

Before editing, inspect the shared continuity coordination receipt. A held owner is a conflict and a stale owner requires manual recovery; neither result changes the lock. Preview a three-way merge only to identify overlaps. When Rush reports `merge_conflict`, reconcile it outside Rush, validate the result, and record a new handoff—there is no automatic merge or retry path.

## 1. Auditing Requirement Traceability
```bash
rush trace
```

## 2. Resolving Multi-Agent Git Merge Conflicts
```bash
rush swarm-merge --base file_base.py --ours file_ours.py --theirs file_theirs.py
```

## 3. Emulating GitHub Actions Locally
```bash
rush simulate-ci --workflow ci.yml
```
