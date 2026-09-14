# ADR-0015 Reviewer identity without a domain: Google-signed ID tokens

Status: accepted (2026-09-14)

## Context

ADR-0008 deferred the load balancer and IAP until a domain exists.  The dev deployment is
now live, the three real orders are at the localisation checkpoint, and the checkpoint and
everything after it (review, publication) are human decisions taken in the web app.  With
the `iap` adapter unconfigured the API refuses every authenticated request, so no reviewer
can act on real material — the Milestone 3–5 gates' real-order parts would stay blocked on
a DNS purchase.

## Decision

- A third identity adapter, `google_id_token`, for the `gcp` profile without a domain.  It
  verifies a Google-signed OpenID Connect ID token (google-auth, Google's public certs),
  requires the issuer to be Google, the email to be verified, and the audience to be one of
  the configured service URLs — our own Cloud Run URLs in both forms (deterministic
  `<name>-<project number>.<region>.run.app` and hashed `<name>-<hash>-<rc>.a.run.app`).  The
  role comes from the `users` table; an unregistered email is `permission_denied`.
- The token reaches the API in one of two ways: `X-User-Id-Token`, forwarded by the web
  service from the `Authorization` bearer it received (the web service uses its own
  metadata-server token for the call itself), or the `Authorization` bearer of a direct call.
- Terraform selects the adapter from the presence of a domain: `iap` with a load balancer,
  `google_id_token` without.  Nothing else in the topology changes: ingress stays internal,
  no public endpoint exists, the VM reaches the services only because it is in the project.
- The operator path is a local proxy on the VM (`scripts/run-proxy.py`, the equivalent of
  `gcloud run services proxy`, which the VM's apt-managed gcloud cannot install), signed in
  as the reviewer's own Google account, tunnelled to the laptop over SSH.  A user account's
  gcloud identity token names gcloud's OAuth client id as its audience, so that id is in the
  accepted list alongside the service URLs; the role still comes only from `users`.  The
  build service account is never a reviewer.

## Consequences

- Reviewer decisions on the real orders are possible now; every decision is attributed to a
  verified Google identity that an administrator registered.
- The audience list is exact, not a pattern: a token minted for a lookalike service in
  another project is refused.  Verification needs Google's public certificate endpoint,
  which the services reach through their non-private egress path (the same path as Secret
  Manager and Cloud Storage).
- When a domain arrives the switch back to IAP is a Terraform variable, and the web service's
  forwarding already covers both headers.
