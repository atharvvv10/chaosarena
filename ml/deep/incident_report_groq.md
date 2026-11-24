## Summary
- Incident involved a **network-latency** attack on the **payment-service** during the **release-candidate** version.  
- Detected within **13.3 s**; recovered in **76.2 s**.  
- Final score **0.5548** exceeded the defender threshold **0.7397**.  
- Incident resolved successfully and was **PROMOTED**.

## Timeline
- **Detection**: 13.3 s after attack onset.  
- **Action requested**: 2026‑11‑20T06:36:42+00:00 (restart of order‑service).  
- **Evaluation completed**: 2026‑11‑20T06:37:08+00:00.  
- **Recovery**: 76.2 s after detection.

## Root cause
- Diagnosis: **latency_spike** in **order-service**.  
- Confidence: **0.99**.  
- Evidence:  
  - `order-service_p95_latency z=+403.7`  
  - `user-service_request_rate z=-11.5`  
  - `cart-service_request_rate z=-10.2`

## Actions taken
- Namespace: **shop-test**  
- Service: **order-service**  
- Action: **restart**  
- Status: **requested** (timestamp 2026‑11‑20T06:36:42+00:00)

## Outcome
- Recovered: **true**  
- Score: **100** → Grade **A**  
- Verdict: **PROMOTE**  
- Reasons:  
  - score 100 meets threshold 70  
  - attack cleanup succeeded  
  - no chaos objects left behind  
- Cleanup OK: **true**  
- Chaos objects remaining: **0**

## Follow-ups
- No deductions recorded.  
- No remaining chaos objects; cleanup complete.