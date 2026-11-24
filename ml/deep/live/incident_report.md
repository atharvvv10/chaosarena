## Summary
- Incident version: **v1.2-deep-aiml**  
- Attack type: **pod-kill** targeting **order-service**  
- Detection: **true** (15.8 s)  
- Recovery: **53.1 s**  
- Final score: **0.766** (below defender threshold **0.8328**)  
- Recovered: **true**  
- Grade: **A**  
- Verdict: **PROMOTE**  

## Timeline
- Detection: **15.8 s** after attack onset  
- Action requested: **2026‑11‑24T12:22:48+00:00** (restart of product‑service)  
- Evaluation completed: **2026‑11‑24T12:23:03+00:00**  
- Total recovery time: **53.1 s**  

## Root cause
- Diagnosis category: **latency_spike**  
- Affected service: **product-service**  
- Confidence: **0.99**  
- Evidence:  
  - `product-service_p95_latency z=+17.3`  
  - `user-service_request_rate z=-14.5`  
  - `product-service_request_rate z=-11.0`  

## Actions taken
- Namespace: **shop-test**  
- Action: **restart**  
- Service: **product-service**  
- Status: **requested** (at 2026‑11‑24T12:22:48+00:00)  

## Outcome
- Recovered: **true**  
- Final score: **0.766** (score 100 meets threshold 70)  
- Cleanup: **ok** (no chaos objects left behind)  
- Chaos objects remaining: **0**  
- Reasons for promotion:  
  1. Score 100 meets threshold 70  
  2. Attack cleanup succeeded  
  3. No chaos objects left behind  

## Follow-ups
- None reported.