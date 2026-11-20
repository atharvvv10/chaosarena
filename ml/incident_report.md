# Incident Report - release-candidate

**Summary**
A `network-latency` fault was injected into `payment-service` in `shop-test` for release candidate `release-candidate`. Resilience score: **100/100 (grade A)**. Gate verdict: **PROMOTE**.

**Timeline**
- Evaluated at: 2026-11-20T06:37:08+00:00
- Fault detected: yes after 13.3 seconds
- Recovery observed: yes after 76.2 seconds
- Chaos cleanup: succeeded
- Chaos objects remaining: 0

**Root cause**
- Category: latency_spike
- Service: order-service
- Confidence: 0.99
- Evidence:
  - order-service_p95_latency z=+403.7
  - user-service_request_rate z=-11.5
  - cart-service_request_rate z=-10.2

**Actions taken**
- `restart` on `order-service` in `shop-test` at 2026-11-20T06:36:42+00:00

**Outcome**
- Returned to normal: yes
- Final anomaly score: 0.5548 (threshold 0.7397)
- Gate reasons:
  - score 100 meets threshold 70
  - attack cleanup succeeded
  - no chaos objects left behind
- Score deductions:
  - None recorded.

**Follow-ups**
- Keep the current baseline and repeat this battle in the next release.