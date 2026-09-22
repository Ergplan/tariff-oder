# Prompt: host a second Docker application on the `tariff-order` VM

Copy everything below the line into a new Claude Code session that runs **on the VM**
(browser SSH).  Fill the three `<...>` placeholders first.  Nothing here is a secret.

---

You are setting up and running a second, unrelated Docker application on a Google Cloud VM
that already serves as the build and operator workstation for another product ("tariff
order studio").  Your job is to host `<APP NAME>` from `<APP REPO URL>` on this VM under
Docker Compose, reachable at `<HOW USERS REACH IT: e.g. only via SSH tunnel / an IAP TCP
tunnel / a public port>`, without touching the existing product.  Work only on this VM and
in this Google Cloud project.  Ask before anything you cannot undo.

## Where you are

| Item | Value |
| --- | --- |
| Google Cloud project | `tariff-order-parsing` |
| VM | `tariff-order`, zone `asia-south2-b`, e2-standard-4, 100 GB disk, Ubuntu 25.10 |
| VM network | the **default** VPC of the project (not the product's VPC) |
| Already installed on the VM | Docker (with compose plugin), Terraform, Node 22, gcloud (Ubuntu archive build, so `gcloud components install` does not work), Claude Code, git, make |
| gcloud identity on the VM | the service account `agent-builder@tariff-order-parsing.iam.gserviceaccount.com` (Editor plus admin roles on this project only); check with `gcloud auth list` and leave it as it is |
| Existing checkout on the VM | `~/tariff-oder` (GitHub `Ergplan/tariff-oder`), pulled over a repo-scoped deploy key in `~/.ssh/id_ed25519_tariff` with a `Host github.com` entry in `~/.ssh/config` |
| Existing Docker use on the VM | image builds for the product (`make build-images` builds and pushes `asia-south1-docker.pkg.dev/tariff-order-parsing/tariff/{python,web}`); an occasional local compose stack from `~/tariff-oder/infra/local/docker-compose.yml` that binds Postgres on 5432 and, when up, an API on 8000 and a web app on 3000 |
| Ports in use or reserved on the VM | 3000, 5432, 5433, 8000 (product), 22 (SSH) — do not use them |

## What exists in the project that you must not modify

The product runs on Cloud Run in `asia-south1`, not on this VM, and is managed by Terraform
from `~/tariff-oder/infra/gcp` with remote state in `gs://tarifforderstudio_tfstate` under
prefix `tariff/dev`.  Everything named `tariff-*` is the product: the VPC `tariff-vpc` and
subnet `tariff-run-asia-south1` (10.10.0.0/24), Cloud SQL, the Cloud Run services and jobs,
the service accounts, Secret Manager secrets (including `ANTHROPIC_API_KEY`), the Artifact
Registry repository `tariff`, the buckets `gs://tarifforderstudio_sources` and
`gs://tarifforderstudio_tfstate` and the `tariff-order-parsing-tariff-*` buckets, the Cloud
Scheduler job, the IAP settings, alerts and budget.

Rules:
- Never run `terraform` in `~/tariff-oder/infra/gcp`, never touch its state prefix, never
  edit files under `~/tariff-oder`.
- Never read, list or use the product's secrets; if your app needs an API key, create your
  own secret with your own name, entered through a terminal prompt (`read -rs`), never on a
  command line, in a file, or in chat.
- Do not change the VM's machine type, disk, service account, scopes or OS login settings,
  and do not stop or restart the VM without asking.
- Do not change firewall rules on the default VPC except to add one rule that you name with
  your app's prefix; do not open a public port without the operator's explicit yes.
- Docker: do not prune images, volumes or networks globally (`docker system prune`,
  `docker volume prune`); the product's build cache and its compose volumes live there.
  Use your own compose project name and your own named volumes.

## How to lay out your application

- Clone to `~/<app-dir>` (not inside `~/tariff-oder`).  If the repo is private, create a
  separate deploy key for it (`ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_<app> -N ""`) and
  add a second `Host` alias in `~/.ssh/config`; do not reuse the tariff deploy key.
- Run it with `docker compose -p <app> -f ~/<app-dir>/docker-compose.yml up -d`.  Bind
  services to `127.0.0.1` on ports outside the reserved list (use 8080-8099 for HTTP and
  5440-5449 for databases unless the app dictates otherwise).  Prefer a `restart:
  unless-stopped` policy so the app survives VM reboots.
- Data goes in named Docker volumes prefixed `<app>_`, or under `~/<app-dir>/data`; check
  free disk first (`df -h /`) and keep at least 20 GB free for the product's image builds.
- If the app needs a Google Cloud resource (a bucket, a secret, Cloud SQL), create it with
  gcloud or with Terraform **in your own directory** with its own state prefix in the same
  state bucket: `bucket = "tarifforderstudio_tfstate"`, `prefix = "<app>/dev"`.  Name every
  resource with the `<app>-` prefix, label it `app=<app>`, and use region `asia-south1` for
  regional resources unless the app requires otherwise.  Prefer `gcloud` for one or two
  resources; use Terraform only if the app has more than that.
- If the app needs its own image in Artifact Registry, create a separate repository
  (`gcloud artifacts repositories create <app> --repository-format=docker
  --location=asia-south1`); do not push into the `tariff` repository.

## Reaching the app

Default to no public exposure: users reach it through an SSH tunnel from their machine,
`gcloud compute ssh tariff-order --zone asia-south2-b --project tariff-order-parsing -- -N -L
<local-port>:localhost:<app-port>`.  If the operator wants a browser URL without a tunnel,
propose IAP TCP forwarding or a small Cloud Run service instead of opening a VM port, and
wait for the answer.

## How to report

Before you start: `df -h /`, `docker ps`, `docker compose ls`, `ss -ltnp` (ports in use),
`gcloud auth list`, `gcloud config list` — and state what you found in one short paragraph.
When done: the compose file path, the ports, the volumes, the commands to start, stop, view
logs and update, any Google Cloud resources you created (with names), and anything you
skipped and why.  Do not claim a step worked unless you ran it and saw the output.
