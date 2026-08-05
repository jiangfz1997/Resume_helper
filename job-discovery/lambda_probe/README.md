# Lambda probe: Indeed + LinkedIn from real Lambda egress

A single manual invocation. CloudShell already showed both sites answer from
AWS address space; this confirms it from Lambda's own egress and from inside
the runtime that would actually be deployed.

Not a scheduled job, not infrastructure. No EventBridge, no SQS, no state.

## Build

```bash
python build.py                 # x86_64, the default
python build.py --arch arm64    # only if the function runs on Graviton
```

Produces `dist/lambda-probe.zip`, about 35 MB zipped and 108 MB unpacked —
inside both the 50 MB console-upload limit and the 250 MB unpacked limit, so
no S3 staging and no container image.

pip resolves manylinux wheels explicitly (`--platform`, `--only-binary=:all:`),
so building on Windows still produces a valid Linux package.

Two things the build does that are not obvious:

- **jobspy is installed with `--no-deps`.** It pins `NUMPY==1.26.3`, which has
  no cp313 wheel; on Python 3.13 pip would fall back to a source build. Every
  other constraint in `DEPENDENCIES` matches jobspy's own declaration.
- **tls-client is pruned to one binary.** Its wheel is `py3-none-any` and
  bundles the Go shared library for every platform: 93 MB of binaries where one
  is used. Which one is counterintuitive — `tls_client/cffi.py` branches on
  `platform.machine()`, and on x86_64 Linux the `"x86" in machine()` test
  matches `x86_64` before the `-amd64.so` branch is reached, so the file
  actually loaded is `tls-client-x86.so`. Pruning to `-amd64.so` builds a
  package that fails at import with a ctypes error. Keeping only the right one
  frees 81 MB and is what brings the zip under the console limit.

## Deploy and run

Console, Create function → Author from scratch:

| Setting | Value |
|---|---|
| Runtime | Python 3.13 |
| Architecture | x86_64 (must match `--arch`) |
| Handler | `lambda_function.lambda_handler` |
| **Timeout** | **120 s** — the default 3 s cannot work, see below |
| **Memory** | **1024 MB** — pandas plus more CPU share |

Upload `dist/lambda-probe.zip` under Code source → Upload from → .zip file.
The console's inline editor will not open a package this size; that is expected.

Test with an empty event `{}` for the defaults, or override any field:

```json
{"search_term": "Software Engineer", "location": "Toronto, ON", "hours_old": 24, "results_wanted": 20}
```

Optional: set the `RESULT_BUCKET` environment variable to have the full result
written to S3. The function needs `s3:PutObject` on that bucket. Leave it unset
and the result is returned in the response and written to CloudWatch Logs.

## Why the timeout matters

Measured locally, 20 results per site:

| Site | Elapsed | Notes |
|---|---|---|
| Indeed | 0.7 s | descriptions arrive with the search result |
| LinkedIn | **26 s** | `linkedin_fetch_description=True` fetches each posting separately |

LinkedIn is 35x slower because the handler asks for descriptions, which costs
one extra request per job. At the default 3 s timeout the function dies before
LinkedIn returns anything, and the failure looks like a block rather than a
timeout. 120 s leaves room for a slower cold start.

This is also the first hard input into the real design: **LinkedIn cannot be
scaled by raising `results_wanted` inside one Lambda.** 20 results already cost
26 s; 50 would approach the limit for a single query-location pair. The task
granularity in the architecture doc — one `source x query x location` per
message — is what keeps this inside a Lambda at all.

## Local run

```bash
../.venv/Scripts/python.exe lambda_function.py
```

Same code path, no AWS. Useful as the residential control before comparing
against the Lambda run.

## Lambda run, 2026-08-05, us-east-1

Egress `3.88.224.162`. Both sites `ok`, 40 rows. This closes the last Phase 0
caveat: aggregator access was confirmed from Lambda's own egress, not only from
CloudShell, and the two sit on different prefixes.

The run was made at the **default 128 MB**, which turned out to be the more
informative configuration:

| | Local (desktop) | Lambda 128 MB |
|---|---|---|
| Indeed | 725 ms | 8 142 ms |
| LinkedIn | 25 979 ms | 116 059 ms |
| Total billed | - | 161 817 ms |

Lambda allocates CPU in proportion to memory, so 128 MB buys roughly a twelfth
of a vCPU. TLS handshakes through the tls-client Go library, JSON parsing and
DataFrame construction are all CPU work, and they stretch 4-11x.

Re-running the same event at 1024 MB:

| | 128 MB | 1024 MB | speedup |
|---|---:|---:|---:|
| Indeed | 8 142 ms | 1 119 ms | 7.3x |
| LinkedIn | 116 059 ms | 22 755 ms | 5.1x |
| scrape total | 124 201 ms | 23 874 ms | 5.2x |

Cost is not the reason to pick one. 128 MB billed 20.2 GB-seconds (~$0.00034);
1024 MB bills roughly 40% more in GB-seconds despite finishing 5x sooner, and
both vanish inside the 400 000 GB-second monthly free tier. **Choose 1024 MB
for timeout headroom, not for cost**, and stop tuning there — chasing the
optimum on a system that costs cents per month is wasted effort.

### The result set is not stable, and only for one source

The two runs were minutes apart with identical parameters.

**Indeed returned the identical 20 postings, same order, same `jk` ids.**

**LinkedIn returned 14 different postings out of 20.** Only six ids survived
both runs (`4420991755`, `4440561026`, `4440391095`, `4446697364`,
`4440547460`, `4447328094`) — 30% overlap, 70% churn, minutes apart.

This splits the two sources into opposite coverage strategies:

- **LinkedIn**: one scrape is a *sample*, not the result set. Repeated runs
  genuinely increase coverage, which is a second reason for the 3x daily
  schedule beyond freshness.
- **Indeed**: deterministic, so repeated runs add nothing. Coverage there comes
  only from more query/location pairs or a larger `results_wanted`. Running it
  more often returns the same 20 rows.

It also constrains the staleness logic, which the architecture doc does not
address: **absence from one run cannot mean the posting closed.** With 70%
churn, most LinkedIn jobs are missing from any given run while still open.
`last_seen_at` may only drive a "gone" decision after several consecutive
misses, and the threshold has to be per-source.

### Description completeness varies enough to matter

Across the same 20 LinkedIn rows, `description_chars` ranged from **170 to
10 831**. A 170-character description cannot be coarse-scored and would burn an
LLM call to produce noise. Coarse scoring needs a minimum-length gate, and the
architecture doc's `description_hash IS NOT NULL` precondition is not enough on
its own.

## Observed on the local control run, 2026-08-04

```
indeed     ok  rows=20    725 ms
linkedin   ok  rows=20  25979 ms
```

Two data-quality facts worth carrying into the schema work:

- **LinkedIn returns no `date_posted`.** All 20 rows had it null. The 24-hour
  window is applied server-side by the `hours_old` search parameter, but the
  response carries nothing to verify or re-filter on. This is exactly why the
  architecture doc keeps `first_seen_at` as the internally reliable field and
  only offers a strict "posted in the last 24h" filter where `posted_at` is
  trustworthy. For LinkedIn it is not.
- **Indeed's relevance is loose.** A `Software Engineer` search returned
  `CNC Machinist/Programmer`. This appeared on both the residential and the AWS
  runs, which settles an earlier open question: it is Indeed's matching, not an
  artifact of a US-datacenter egress IP. Title-level filtering is not optional.
