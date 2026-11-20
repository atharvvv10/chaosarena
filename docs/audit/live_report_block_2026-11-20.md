# Incident Report - release-candidate

1. Summary
A `network-latency` fault was injected into `payment-service` in `shop-test` for release candidate `release-candidate`. Resilience score: 65/100 (grade D). Gate verdict: BLOCK.

2. Timeline
- Evaluated at: 2026-11-20T14:42:17+00:00
- Fault detected: yes after 0.0 seconds
- Recovery observed: no
- Chaos cleanup: succeeded
- Chaos objects remaining: 0

3. Root cause
- Category: latency_spike
- Service: product-service
- Confidence: 0.99
- Evidence:
  - order-service_p95_latency z=-156.2
  - payment-service_p95_latency z=-58.4
  - user-service_request_rate z=+43.6

4. Actions taken
- `restart` on `product-service` in `shop-test` at 2026-11-20T14:41:13+00:00

5. Outcome
- Returned to normal: no
- Final anomaly score: 1.1184 (threshold 0.7397)
- Gate reasons:
  - score 65 is below threshold 70
  - attack cleanup succeeded
  - no chaos objects left behind
- Score deductions:
  - service did not return to a normal score (-25)
  - final anomaly score is still above threshold (-10)

6. Follow-ups
- Investigate why the service did not return to baseline quickly.