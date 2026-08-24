# Acceptance and continual-improvement gates

Run `~/prime-dgx-agent/validate.sh` before and after every runtime or model
change. A candidate cannot be accepted unless both model endpoints are healthy,
loopback-only, and the idle machine retains at least 20 GiB available memory.

For agent behavior, keep a frozen prompt set covering: tool selection and
delegation, a dimensioned printable part with tolerances, a timestamped
portfolio critique, rejection of a live-order request, an image/chart reading,
and a small coding repair with tests. Record model/config version, latency,
quality rubric results, and regressions. Promotion requires no safety regression
and an explicit human review; rollback is the default response to degradation.
