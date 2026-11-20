# Incident Report - release-candidate

1. Summary
A `network-latency` fault was injected into `payment-service` in `shop-test` for release candidate `release-candidate`. Resilience score: 70/100 (grade C). Gate verdict: PROMOTE.

2. Timeline
- Evaluated at: 2026-11-20T14:47:24+00:00
- Fault detected: no
- Recovery observed: yes after 37.2 seconds
- Chaos cleanup: succeeded
- Chaos objects remaining: 0

3. Root cause
- Category: not recorded
- Service: not recorded
- Confidence: not recorded
- Evidence:
  - None recorded.

4. Actions taken
- No remediation action was taken.

5. Outcome
- Returned to normal: yes
- Final anomaly score: 0.632 (threshold 0.7539)
- Gate reasons:
  - score 70 meets threshold 70
  - attack cleanup succeeded
  - no chaos objects left behind
- Score deductions:
  - fault was never detected (-30)

6. Follow-ups
- Add a detector for this fault family before the next release.