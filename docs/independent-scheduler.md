# Activate the independent morning clock

GitHub scheduled events were arriving after the noon cutoff. cron-job.org provides
the independent clock; GitHub Actions continues to collect, review and send.
The Resend credentials remain in GitHub Secrets and never go to cron-job.org.

The prepared schedule uses **America/New_York**, including daylight saving time:

| Private cron-job.org job | Local times | Action |
| --- | --- | --- |
| Preparation and recovery | 04:37, 05:37, 06:37, 07:37 | Dispatch `daily-news.yml`, mode `daily` |
| Delivery audit | 08:15 | Dispatch `verify-morning-delivery.yml` |

An early-ready edition waits for **08:00** before sending. The existing durable
ledger prevents duplicate daily emails when recovery triggers overlap. GitHub's
native schedule remains a backup. The audit checks the actual daily send timestamp
and provider delivery, not just whether GitHub accepted the HTTP trigger.

## One-time secure setup

1. Create and verify a free account at <https://console.cron-job.org>. Under
   **Settings → API**, generate an API key. Hosted GitHub runners have changing IP
   addresses; an optional IP restriction must allow the runner if you enable it.
2. Create a GitHub **fine-grained personal access token** at
   <https://github.com/settings/personal-access-tokens/new>.
   Select resource owner **maxwuqitian-ai**, only repository **max-news**, and
   repository permission **Actions: Read and write**. No content-write or
   secrets-read permission is needed. Choose an expiration you can maintain and
   replace the token before it expires.
3. At <https://github.com/maxwuqitian-ai/max-news/settings/secrets/actions>, add
   these **Repository secrets**, using the exact names:

   | Secret | Value |
   | --- | --- |
   | `CRONJOB_API_KEY` | The cron-job.org API key |
   | `NEWS_DISPATCH_TOKEN` | The narrowly scoped GitHub token |

   Keep `RESEND_API_KEY`, `NEWS_SENDER` and `NEWS_RECIPIENT` unchanged. Do not put
   credentials in chat, source files or Codex environment settings.
4. Run **Actions → Configure independent morning clock → Run workflow** with
   action **apply**. The assistant can dispatch this once the secrets are present.

The setup first checks GitHub workflow access and starts a **check** run that
cannot collect news or send email. It then creates or updates only its two named
jobs and reads back their private settings. Repeating setup updates the same jobs.
Incomplete listings, duplicate managed titles, wrong endpoints, authorization
errors and readback mismatches fail instead of claiming successful activation.
An uncertain API write is not retried within the command; reconcile existing jobs
before another apply. Unrelated jobs are never deleted or modified.

The GitHub dispatch token is stored as a **private request header** in these two
cron-job.org jobs. Its narrow repository scope limits access. The cron-job.org API
key remains in GitHub Secrets; it is not placed in the scheduled requests.
Treat the scheduler account as confidential and protect it with account security.

## Verify activation

Run the same workflow with action **verify**. It performs read-only checks of the
two jobs and prints only safe job IDs, timezone, hours and enabled status.
`plan` needs no credentials and applies no changes:

```sh
python -m news_agent.external_scheduler plan
gh workflow run configure-scheduler.yml --ref main -f action=apply
gh workflow run configure-scheduler.yml --ref main -f action=verify
```

The plan includes no credential values. Never paste private API responses or job
headers into public logs. The setup command omits response bodies from errors.

After credentials are configured, relevant pushes to `config.yaml`, the scheduler
module or setup workflow automatically reconcile the two jobs. The target time,
preparation lead and timezone derive from `newsletter` configuration;
`scheduler.ref` defaults to `main`. Rerun **apply** after rotating either key.

## What constitutes success

- Setup readback confirms that the two external jobs exist and are enabled.
- A successful scheduled HTTP request means GitHub **accepted** a dispatch.
- A successful real morning audit means the daily send was recorded between
  **08:00:00 and 08:01:00 New York**, and Resend confirmed delivery to the right
  recipient. It does not prove the precise second an inbox displays the email.

cron-job.org account notifications cover rejected HTTP triggers or disabled jobs.
GitHub Actions failure notifications cover generation or delivery-audit failures;
enable those in your GitHub notification settings if you want inbox alerts.
The free scheduler and hosted runner remain best-effort services, so punctuality
must be measured on real runs. Source and freshness failures still block mail.

Until **apply** succeeds, the external clock is **not active**. Unit tests and a
plan alone do not restore delivery. No test newsletter is sent by setup or verify.

API contract: [official cron-job.org REST documentation](https://docs.cron-job.org/rest-api.html)
and its [official source](https://github.com/pschlan/cron-job.org/blob/master/docs/source/rest-api.rst).
