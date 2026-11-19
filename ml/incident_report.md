# Incident Report - v1.0.3

## Summary
A `network-latency` fault was injected into `payment-service` in `shop-test` for release candidate `v1.0.3`. Resilience Score: **100/100 (grade A)**. Gate verdict: **PROMOTE**.

## Timeline
- Evaluated at: 2026-11-19T12:35:18+00:00
- Fault detected: yes after 14.0 seconds
- Chaos cleanup: succeeded
- Chaos objects remaining: 0

## Root cause
- Category: latency_spike
- Service: order-service
- Confidence: 0.99
- Evidence:
  - order-service_p95_latency z=+289.5
  - payment-service_request_rate z=-7.5
  - product-service_request_rate z=-7.0

## Actions taken
- `restart` on `order-service` in `shop-test` at 2026-11-19T12:35:04+00:00

## Outcome
- Returned to normal: yes
- Gate reasons:
  - score 100 meets threshold 70
  - attack cleanup succeeded
  - no chaos objects left behind
- Score deductions:
  - None recorded.

## Follow-ups
- Keep the current baseline and repeat this battle in the next release.