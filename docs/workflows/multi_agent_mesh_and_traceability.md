# Workflow: Multi-Agent Mesh Coordination & Traceability

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
