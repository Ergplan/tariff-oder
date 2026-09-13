# ADR-0004 Platform adapter interfaces and local defaults

Status: accepted (Milestone 0/1)

## Decision
`tariff_api.adapters` defines `ObjectStore` (put/get/stream/exists/health over logical
buckets `sources`, `artefacts`, `exports`), `SecretProvider` (get), `IdentityProvider`
(authenticate(headers, role_lookup)).  `build_adapters(settings)` selects implementations
from `DEPLOYMENT_PROFILE` plus explicit backend settings; `Settings.validate_profile()`
refuses local-only adapters under `gcp`, and `LocalIdentityProvider` refuses to construct
under `gcp` on its own.

Local object store default is the **filesystem** implementation (same key scheme, atomic
writes, immutable keys).  MinIO is provided in compose behind the `minio` profile for
developers who want bucket semantics, but no S3 client is a runtime dependency until an S3
adapter is needed.

## Consequences
Cloud SDK imports happen lazily inside the gcp adapters, so the local profile needs no
Google credentials.  IAP audiences are a comma-separated list because the API receives
assertions minted for both the web and the API backend services.
