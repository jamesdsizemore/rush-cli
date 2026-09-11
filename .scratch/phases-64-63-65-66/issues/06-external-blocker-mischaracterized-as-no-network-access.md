# "No outbound network access" external-blocker language is inaccurate -- the real gap is no published GitHub release

Status: needs-triage

## Observed evidence

Multiple receipts on this board (P65-01/T200-T201, P65-02/T202-T203, and P65-10/T210/T024/T025) named their clean-machine/live-network acceptance gap as "no outbound network access in this sandbox." T211's adversarial review of P65-10 (board `phases-64-63-65-66`) tested this directly and found it false: `curl https://github.com` returns 200, and `curl https://api.github.com/repos/jamesdsizemore/rush-cli/releases/latest` returns 404 -- the sandbox has real outbound network access; there is simply no published GitHub release for this repository yet, so there is nothing to download.

PM independently reproduced both results in this session.

## Intervention assessment

The practical conclusion every one of those receipts drew ("cannot run a real clean-machine install against a live published release in this environment") is still correct and remains a genuine, real blocker -- just for a different reason than stated. This is a receipt-accuracy issue, not an implementation defect: no code needs to change, but every future receipt should describe this gap as "no published GitHub release exists yet to download," not "no outbound network access," since the latter is checkable and false, and a future session that trusts the stated mechanism without re-verifying could waste time debugging a nonexistent network restriction.

## Scope

No task-specific fix needed. This is a documentation/receipt-language correction to carry forward: any future task on this board (or a later phase) that needs to name this same class of external blocker should use the corrected, verified phrasing. If/when a real GitHub release is published for this repo, the actual live-network clean-machine acceptance test becomes runnable and should be executed for real rather than named as a blocker at all.
