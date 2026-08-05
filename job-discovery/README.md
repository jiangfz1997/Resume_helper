# job-discovery

Flow 1 of the job pipeline: scheduled discovery, normalization, dedup, hard
filtering and coarse scoring. Resume generation is a separate product boundary
and is not implemented here.

Current contents: the Phase 0 reachability probe only. No infrastructure is
committed until the probe says which sources are worth building adapters for.

## Phase 0: does an AWS egress IP reach the sources at all?

The whole cloud design collapses if the target sites refuse traffic from AWS
address space. This probe answers that before any SAM template exists.

### The rule that makes the result meaningful

Run the probe **from your own machine first**. Without a residential baseline,
a zero-result run on AWS is unattributable: blocked IP, wrong search term, and
a stale endpoint all look identical. Every verdict in `--compare` is a
difference between two runs, never a single absolute number.

### Two tiers, two levels of confidence

| Tier | Sources | How it is probed | Confidence |
|---|---|---|---|
| A | Workday CXS, Greenhouse, Lever | stdlib `urllib`, endpoints reimplemented here | high |
| B | Indeed, LinkedIn, Glassdoor, ZipRecruiter | `jobspy.scrape_jobs()` called directly | high |

Tier B must go through jobspy itself. jobspy relies on `tls-client` for TLS
fingerprint impersonation; a hand-written HTTP request gets refused earlier
than the real crawler would, which produces false "blocked" verdicts and kills
usable sources.

jobspy also swallows transport failures and returns an empty DataFrame rather
than raising, so the probe attaches a handler to jobspy's own loggers
(`propagate` is off, a root handler sees nothing) and classifies from the
status codes found there. Without this, a 403 is indistinguishable from
"no jobs matched".

### Outcomes

| Outcome | Meaning |
|---|---|
| `ok` | postings returned |
| `empty` | 200/no error, zero postings — the silent failure mode |
| `blocked` | 401/403/407/429/451, or a challenge marker in the body |
| `not_found` | 404/410, stale board token or endpoint — **not** an IP problem |
| `error` | other non-2xx or a transport exception |
| `skipped` | jobspy not installed (Tier A can still run) |

`not_found` is separated from `blocked` on purpose: a rotated Greenhouse token
must never be reported as AWS being firewalled.

## Running it

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-probe.txt   # Windows
# source .venv/bin/activate && pip install -r requirements-probe.txt  # Linux

python -m probes.run --env local-baseline --out reports/local-all.json
```

Then in [AWS CloudShell](https://console.aws.amazon.com/cloudshell) — browser
only, nothing to deploy, no cost. Upload `probe-bundle.zip` via
`Actions > Upload file`:

```bash
unzip -o probe-bundle.zip

# Tier A needs nothing installed; CloudShell ships pydantic and pyyaml.
python -m probes.run --env aws-cloudshell --tier ats --out reports/aws-ats.json

# Tier B, see the Python 3.13 note below.
pip install -r requirements-tierb.txt
pip install --no-deps "python-jobspy>=1.1.82"
python -m probes.run --env aws-cloudshell --out reports/aws-all.json
```

Compare:

```bash
python -m probes.run --compare reports/local-all.json reports/aws-all.json
```

### Installing Tier B on Python 3.13

`pip install python-jobspy` fails on CloudShell. jobspy pins `NUMPY==1.26.3`,
which predates Python 3.13 and has no cp313 wheel, so pip tries a source build
and CloudShell has no compiler:

```
ERROR: Unknown compiler(s): [['cc'], ['gcc'], ['clang'], ...]
```

Do not install a compiler for this. Install the dependencies explicitly with a
numpy that has cp313 wheels, then jobspy with `--no-deps`:

```bash
pip install -r requirements-tierb.txt
pip install --no-deps "python-jobspy>=1.1.82"
```

Every constraint in `requirements-tierb.txt` matches jobspy's own declaration
except numpy. Verified on Python 3.13 with numpy 2.5.1 and pandas 2.3.3:
Indeed and LinkedIn both return rows. pip will still print a warning about the
unmet `NUMPY==1.26.3` pin; that is the intended deviation.

`pip install --user` also fails in CloudShell (its default interpreter is
already a virtualenv). Install without `--user`.

`IP-BLOCKED` rows are sources that worked from home and stopped working from
AWS. That list, and only that list, is what a proxy budget would buy back.

### Why CloudShell and not Lambda

CloudShell exits through AWS ASN 16509, the same address space as Lambda, and
opens in about a minute with `pip` available. Blocking is applied at ASN/prefix
level, so the verdict transfers. Probing from Lambda itself needs an ECR image
(jobspy pulls pandas and curl_cffi, which is awkward as a zip) and is worth
doing only once an adapter is actually being deployed.

## Result, 2026-08-04

Both runs used the same 15 targets and the same jobspy 1.1.82.

| Source | Residential (AS812 Rogers) | AWS (AS14618, 13.220.219.9) |
|---|---|---|
| Workday x6 (wd3/wd5/wd10/wd12) | ok | ok |
| Greenhouse x3 | ok | ok |
| Lever x2 | ok | ok |
| Indeed CA | ok, 10 rows | **ok, 10 rows** |
| LinkedIn | ok, 10 rows | **ok, 10 rows** |
| Glassdoor | error 400 | error 400 |
| ZipRecruiter | blocked 403 | blocked 403 |

**No source degraded on AWS egress.** Nothing appears only on the residential
baseline, so there is no proxy budget to justify — that was the largest single
cost variable in the plan.

Two sources fail everywhere, for reasons that have nothing to do with AWS:

- **ZipRecruiter**: 403 from both egresses, Cloudflare WAF
  (`forbidden cf-waf` on AWS, `forbidden aa` residential). No proxy fixes a WAF
  rule that also rejects a residential IP. Drop the source.
- **Glassdoor**: broken upstream in jobspy 1.1.82. Its location lookup returns
  400 for every location tried — Toronto, New York, San Francisco, London —
  from both egresses. Not a location-format problem, not a block, not fixable
  from config. Excluded from v1; the target stays in `targets.yaml` so a jobspy
  upgrade is detected on the next run.

### What this does not prove

- **CloudShell is not Lambda.** Same ASN, different prefixes. Transferable, not
  proven; confirm once an adapter is actually deployed.
- **One request is not sustained load.** Aggregator blocking is usually applied
  on volume and pattern, not on request one. Ten results at one query proves
  nothing about 3 runs/day x N query-location pairs over weeks. Treat Indeed
  and LinkedIn as degradable sources: per-source health metrics, empty-result
  alarms, and the ability to disable them without touching the ATS path.
- **Result relevance may differ by egress geography.** The top Indeed row for
  the same Toronto query was `Senior Business Applications Developer`
  residentially and `CNC Machinist/Programmer` from us-east-1. Ordering churn
  is the likely explanation, but a US-datacenter IP degrading Canadian result
  quality would be a data-quality problem that no status code exposes. Worth
  watching once volume is real.

### Source list this justifies for v1

1. Workday CXS, Greenhouse, Lever — sub-second, hundreds of postings per call,
   stable JSON. Build these first.
2. Indeed and LinkedIn via jobspy — usable, but carry the dependency cost below
   and must be independently disableable.
3. ZipRecruiter, Glassdoor — excluded.

## Adding targets

Edit `probes/targets.yaml`. Workday entries need `tenant`, `site_id` and the
shard-specific `base_url`; the committed set deliberately spans wd3/wd5/wd10/wd12
because shards sit behind different edges and can be blocked independently.

Verify a Greenhouse token with
`https://boards-api.greenhouse.io/v1/boards/<token>/jobs` and a Lever slug with
`https://api.lever.co/v0/postings/<company>?mode=json` before adding them.

## Licensing note

ApplyPilot is AGPL-3.0-only. This project reimplements the endpoint shapes and
reuses the Workday tenant registry as factual data; it does not copy ApplyPilot
source. Keep it that way unless this project is also going AGPL, because
serving it over a network triggers the source-disclosure obligation.
