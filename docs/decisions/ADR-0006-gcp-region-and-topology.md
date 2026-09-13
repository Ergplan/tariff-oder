# ADR-0006 Google Cloud region, project layout and worker shape

Status: accepted provisionally (Milestone 0); apply blocked

## Decision
- Region `asia-south1` (Mumbai) for all data-bearing services (Cloud SQL, buckets, Cloud
  Run, Artifact Registry).  Reason: Indian data residency and latency; single region keeps
  private networking simple.  `asia-south2` (Delhi) is the fallback if a service or quota is
  unavailable.
- Separate projects per environment (`dev`, optional `staging`, `prod`) from one Terraform
  root with per-environment tfvars and a per-environment remote state bucket.
- Worker shape for Milestone 1: Cloud Run Job triggered by Cloud Scheduler draining the
  queue.  Milestone 8 re-decides after measuring the 570-page KERC and 423-page NPCL runs.
- Identity: global external HTTPS load balancer + IAP in front of Cloud Run; Cloud Run
  ingress limited to the load balancer.

## Verification status
Terraform validated offline with pinned providers.  Google Cloud documentation was not
reachable from the build environment (proxy 403); pricing/limits must be re-verified by the
operator before the first apply (checklist in docs/deployment.md).  No plan or apply was run.
