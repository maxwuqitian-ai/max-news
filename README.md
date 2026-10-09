# Global Daily News Agent / 全球每日新闻

A Python MVP for a personal Simplified Chinese daily briefing: a variable 4–15 distinct, consequential global events, original publisher links, source-backed facts and context, responsive HTML and plain text. Summaries use plain Chinese, short sentences and essential context, without repeated generic audit disclaimers. Stories are organized into 政治与国际关系、经济与市场、公司与商业、科技与AI. Section sizes vary with the day’s consequential developments, with no fixed category counts. Topic selection stays globally consequential; economics and business receive substantive coverage. There are no fixed country quotas or weekly recaps. Ongoing events can recur on subsequent days.

**Daily scheduling is enabled for 08:00 America/New_York at the user’s request.** The reviewed manual sample was accepted by Resend. Automated generation remains unverified and fails closed; set `newsletter.delivery_enabled: false` to pause scheduling. Resend is the primary provider; a Gmail OAuth adapter is also included.

## Local development

Python 3.11+ is required (tested with 3.12). Use the existing checkout; cloud tasks are isolated and need no additional worktree.

```bash
cd /workspace/max-news
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pytest -q
.venv/bin/python -m news_agent collect
```

`collect` needs no model key. It writes normalized articles and a source availability report in the ignored `output/` directory. It fails if no usable sources are available. Source outages are logged independently; blocked publisher pages can fall back to the publisher's own RSS evidence. The final editorial gate must still find enough evidence and source diversity.

For generation, the default is **local Ollama + Qwen 3.5 9B**, with no API subscription:

```bash
./scripts/install_ollama.sh
./scripts/start_ollama.sh
OLLAMA_HOST=127.0.0.1:11434 .tools/ollama/bin/ollama pull qwen3.5:9b
.venv/bin/python -m news_agent preview
```

The installer pins Ollama 0.40.1 and verifies the official SHA-256 before extracting it. Ollama validates model content digests when pulling weights. The runtime binds only to loopback; model weights remain under ignored `.models/`. Ollama also needs write access to its generated signing-key directory at `~/.ollama`; do not change `HOME` to work around this. Around 10 GB of free disk and 16 GB of RAM are recommended. CPU generation may take tens of minutes. The local pipeline classifies sources in small batches, then Python groups matching event keys and ranks a varied selection; it audits each selected event before writing and verifying every story in bounded contexts, followed by an edition-level duplicate/quality review. A failed review prevents sending.

For an optional hosted model, set `model.provider: openai`, an HTTPS `base_url` such as `https://api.openai.com/v1`, `name: gpt-4.1`, and `api_key_env: NEWS_LLM_API_KEY` in `config.yaml`. Set that key securely in the runtime and GitHub Secrets. A ChatGPT subscription is separate from OpenAI API billing. The default local configuration needs no OpenAI key.

Preview writes:

- `output/briefing.html` and `output/briefing.txt`: rendered edition.
- `output/edition.json`: stories, scores, claim-level evidence and review result.
- `output/articles.json`: retrieved source evidence, publisher URLs and timestamps.
- `output/collection-report.json`: current-run source failures and collection count.

Open the HTML file locally and review accuracy, Chinese phrasing, balance, duplicate events and source links. These are private local artifacts, not web publications. Synthetic test fixtures are never a real-news sample.

## Configure delivery

Set `NEWS_RECIPIENT` to your recipient address in GitHub Secrets and your local/cloud runtime. Keep the address out of source configuration. Also set:

| Secret | Purpose |
| --- | --- |
| `RESEND_API_KEY` | Resend send permission; restrict it to the sender's domain when possible |
| `NEWS_SENDER` | Sender address on a domain verified in your Resend account |
| `NEWS_RECIPIENT` | One recipient address |

An account/API key alone is insufficient for arbitrary delivery. Verify your sending domain in Resend and use a sender on that domain; the default Resend sandbox sender has recipient restrictions. See [Resend domain verification](https://resend.com/docs/dashboard/domains/introduction) and [sending emails](https://resend.com/docs/api-reference/emails/send-email). Do not paste keys into chat or commit them.

After preview succeeds, manually send the **reviewed current-day edition**:

```bash
.venv/bin/python -m news_agent send-test --test-id first-inbox-check
```

`send-test` sends a real email with `[测试]` in the subject without waiting for the daily target time. Reuse the same test ID to prevent duplicate tests. This is separate from preview, which never sends. Check your inbox and spam folder, mobile formatting, plain-text alternative and source links. API acceptance is not proof of inbox arrival; confirm receipt yourself before enabling the workflow.

### Optional Gmail delivery

Set `email.provider: gmail` and securely provide `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, and `GMAIL_REFRESH_TOKEN`. Enable the Gmail API in a Google Cloud project, configure an OAuth consent screen and authorize your own Gmail account through Google's installed-app OAuth flow. Request **only** `https://www.googleapis.com/auth/gmail.send` and offline access. Store the refresh token in Secrets; never commit downloaded client JSON or tokens. A refresh response advertising broader scopes is rejected. A consent screen in external Testing status can cause refresh tokens to expire after seven days; configure an appropriate consent status for durable personal use. See [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) and [Google OAuth offline access](https://developers.google.com/identity/protocols/oauth2/web-server#offline).

## GitHub Actions and activation

1. Push/review this implementation on GitHub (this workspace does not push automatically).
2. Add the required values under repository **Settings → Secrets and variables → Actions**.
3. Run **Daily Chinese news → Run workflow → preview** and review its artifacts.
4. Run the workflow with `send-test` and a stable test ID; verify inbox receipt.
5. Only then set `newsletter.delivery_enabled: true` in `config.yaml` and commit the change to the default branch.

GitHub cron uses UTC. The workflow covers both UTC offsets, while Python's `zoneinfo` enforces `America/New_York`. Preparation starts up to 210 minutes before the 08:00 target (04:30 local), with the first eligible scheduled tick at 04:37 and a four-hour job budget, giving CPU inference time to finish. An early edition waits until 08:00 before sending. Backup ticks recover delayed jobs within a four-hour send window; delivery is never attempted before 08:00 or after 12:00 local. **GitHub Actions can delay or drop schedules, and local inference can exceed its preparation window; exactly 08:00 is a target, not a guarantee.** Preparation lead time is editable in configuration. There is no weekly job. The workflow downloads and caches the local runtime/model on hosted runners; no paid inference API is needed.

The workflow is serial across manual and scheduled runs. Its `contents: write` permission maintains a dedicated `news-agent-state` branch containing only the delivery ledger. Branch rules must allow the workflow to write that branch. No application branch is changed by delivery. Artifacts retain source evidence for seven days; review retention and repository access for your personal use.

## Delivery safety and failures

- A durable `pending` record is pushed **before** the email API request. Failure to persist it aborts delivery.
- Resend also receives an idempotency key. The repository ledger protects beyond the provider's idempotency window and across Actions machines; local use uses a file lock and atomic, fsynced JSON.
- A successfully sent edition is skipped for the same recipient/day even if the provider changes. A new day allows fresh coverage of ongoing events.
- An ambiguous timeout, cancellation or uncertain send is **not automatically retried**. This chooses avoiding duplicate emails over potentially sending a second copy. Review Resend/Gmail delivery logs; reconcile the ledger only after determining whether a message was accepted. Do not delete the state branch to fix an error.
- If accepted, preserve the record and mark `sent` with the provider message ID. If definitively not accepted, remove only that one attempt after stopping other delivery jobs, then rerun. Never reset an uncertain attempt merely because no email has arrived yet.
- Safe source GET requests retry transient errors; model and mail POST requests do not blindly retry. Logs omit credential values and API response bodies.
- Insufficient stories, source diversity, exact evidence quotes, duplicate events, excess technology stories or a failed independent model review cause generation to fail rather than pad the edition or send unverified content.

## Hanover weather and concise writing

The top of each email shows Hanover, New Hampshire weather in Celsius: current temperature, daily low/high, and rain/snow probability. Open-Meteo's public forecast API is free for personal noncommercial use and requires no key. Location name and coordinates are editable in `config.yaml`. Weather is refreshed after any scheduled wait, immediately before rendering/sending. If the request fails or values/timestamps cannot be verified, the header says weather is unavailable rather than guessing.

The probability is the **highest hourly precipitation probability** during the forecast day, including snow; it is not the probability of any rain over the entire day. Morning editions show today's range/probability; previews after 18:00 show tomorrow's forecast with an explicit label. Current temperature has its own timestamp in the audit JSON. Open-Meteo attribution appears with the weather header.

News summaries retain complete publisher sentences, usually up to 220 Chinese characters, covering what happened and essential context when available. Necessary attribution and forecast/proposal versus fact distinctions remain. Generic repeated verification paragraphs are omitted from the email, while claim-level quotes and cross-check records stay in the audit JSON. Estimated reading time is calculated from the actual copy instead of padding to ten minutes.

## Daily freshness and topic balance

Each edition uses publisher reports published within the preceding 24 hours and identifies a specific substantive new development with an exact supporting passage. Republishing an old story, an explainer/profile or a roundup does not make it eligible. Ongoing events may return only with new verified developments. Older facts can appear as necessary, clearly sourced background.

The email shows a compact New York cutoff, grouped stories, weather and original publisher links. Publication timestamps and verification details remain in the audit JSON. Static previews carry a short sample label. Early preparation excludes reports that would be older than 24 hours at the intended send time. Before sending, the agent rechecks that the edition is at most four hours old and every story's new-development source remains within the 24-hour window; it fails rather than send stale news.

The edition has no fixed category or country quotas. Section sizes vary by daily newsworthiness. Validation requires coverage across at least three sections and applies proportional limits to prevent politics/world, conflict or technology from dominating. It rejects an insufficiently varied edition rather than filling gaps with stale or low-impact content. BBC Technology and The Guardian Business feeds supplement broader news discovery. Diversity settings, proportional limits and section order are editable in `config.yaml`.

## Editorial and evidence limits

The pipeline normalizes tracking URLs and filters stale/future publication timestamps. The local model assesses every source in small batches and assigns reusable event keys across languages. Python groups those keys, ranks distinct events and applies proportional topic limits; a separate per-event audit checks genres, categories, duplicate events and actual new developments. The optional hosted pipeline also provides conservative preliminary lexical groups to its editor. Ranking weights are consequence 40%, timeliness 20%, credibility 20%, global relevance 20%. Every fact/context paragraph must cite an exact retrieved passage; a second model pass checks entailment, translations, Chinese quality, headline wording, independence and event duplication.

GDELT is a multilingual **discovery** service. Its `seendate` is stored as discovery time. A GDELT article is eligible only when the publisher supplies a timezone-aware publication timestamp through article metadata/JSON-LD and that timestamp is within the window; unknown or stale publication dates are excluded. RSS entries without a publication timestamp are also excluded. A discovery time or updated timestamp alone never qualifies a story as fresh. Publisher family labels alone do not establish independent reporting: a syndicated copy is one reporting origin. Independent corroboration is required when available and disclosed per story; single-source reporting is labeled. These checks reduce errors but are not a guarantee of truth. Human review of the initial sample remains required.

Publisher HTML can be unavailable or contain boilerplate, and RSS excerpts may be too short for context. The agent must omit unsupported context or fail the edition. It does not bypass paywalls or invent evidence. Sources, model, editorial preferences, counts and delivery settings are in `config.yaml`.

## Real-source sample and current validation

An assistant-edited sample is available in [`samples/briefing.html`](samples/briefing.html) and [`samples/briefing.txt`](samples/briefing.txt), with 12 stories, 13 original publisher reports and a claim-level evidence file. It uses the live collection retrieved on October 7, 2026 in New York time. It is a static editorial example, **not** proof that the local-model pipeline ran successfully. The revised sample follows the four-section mix and includes just one conflict story, alongside markets, trade, taxation, earnings, acquisitions, restructuring, competition investigations and technology releases. Original publisher links were fetched successfully during collection.

Current cloud validation: **128 tests pass**, including repeat installation/startup of the saved environment script. The pinned Ollama runtime and Qwen 3.5 9B model are installed and verified against official artifacts. A real five-story source-preserving local preview completed final model approval and programmatic evidence checks. Truncated RSS fragments are omitted, then remaining stories are rebalanced without relaxing source, consequence, freshness or category checks. The minimum was changed to four because the user permits variable counts; a quiet or source-limited day is never padded.

Automatic generation and delivery passed in [37858263255](https://github.com/maxwuqitian-ai/max-news/actions/runs/37858263255). It revalidated the original current-day collection (October 8, 2026, 17:37 New York), approved four publisher-grounded stories across politics, economics and business, refreshed Hanover weather, passed send-time freshness checks, and sent one test email at 19:41 New York. The durable ledger records the stable test identity as sent. Read-only provider check [37860936500](https://github.com/maxwuqitian-ai/max-news/actions/runs/37860936500) confirmed `delivered` and recipient match; provider message ID is `01a11de4-e3ee-7f0b-a2b5-6849abc7e5f9`. This validates automatic generation and delivery on one real collection; it does not guarantee that every future day will have sufficient approved news or that GitHub starts exactly on time.

Earlier full runs failed editorial checks before sending. Repairs count military tests/naval confrontations and ceasefire/attack decisions toward conflict limits, alternate feeds within publisher families and filter lottery/routine monthly-revenue headlines before candidate limits. Report comparison reads authentic source headlines and excerpts with a bounded reasoning pass. The final audit uses the actual email section order; explicit empty issue markers are normalized only after genuine positive assessments, preserving negative assessments and substantive issues. GitHub repository mail secrets work; the separate Codex Resend credential fails authentication.

Recurring delivery is enabled at the user's explicit request, targeting **08:00 America/New_York** with daylight saving adjustment. Generation uses the free local model; GitHub Models is unavailable because the service was retired July 30, 2026 ([official GitHub documentation](https://github.com/github/docs/blob/main/content/github-models/index.md)). Source/freshness validation and final editorial approval are mandatory before delivery. Exact-input model checkpoints never override these checks. Saved Codex environment instructions require review and publication in environment settings; that development-environment configuration is separate from the deployed GitHub workflow.

## Development checks

`python -m pytest -q` covers normalization, source outages, publication-vs-discovery time, redirects, citation/claim validation, Chinese rendering, technology limits, independent review rejection, Gmail MIME/scope handling, uncertain-send behavior, day-by-day duplicate prevention, daylight saving transitions, and durable state restoration against a local bare Git repository. Network and mail calls in unit tests are synthetic/mocked, not a real delivery test.

The default editorial mode is now `publisher_chinese_excerpt`: the free local model ranks, groups and audits news, while Chinese headlines and complete summary sentences remain verbatim publisher text with deterministic Traditional-to-Simplified conversion. This prevents invented names, dates and figures during rewriting. Headline facts appear once in the email; original publisher links remain visible. Sources include official Chinese RSS from CNA (its publisher-linked FeedBurner feeds), FT, NYT, BBC, DW, RFI and TechNews, alongside multilingual GDELT discovery and other reputable RSS feeds. Publisher page publication metadata takes priority; RSS update-only dates remain discovery observations until original publication is verified. All collected languages participate in event grouping; a publishable Chinese primary is required, so English-only events currently cannot enter this deterministic excerpt mode. Grouped English and Chinese reports are compared even when a secondary report cannot fit the email. Conflicts, unrelated reports or materially superseded copy are rejected; multiple publisher names never automatically imply independent reporting. Before mailing, every excerpt is rechecked against its publisher evidence and fresh publication timestamp. A 45-minute freshness buffer is applied after the intended send target when preparing early, excluding reports likely to expire around delivery. Generated/paraphrased local copy remains experimental and is not the default. A real current-day automatic edition passed generation, freshness validation and delivery as recorded above. Editions still stop before sending if source, freshness or editorial checks fail.

On October 9, 2026, scheduled generation failed on the first two attempts and the recovery run sent at 11:34 New York instead of 08:00. The preparation window now begins one hour earlier and the first scheduled tick avoids the busy hourly boundary. This gives inference/recovery more time; it does not establish punctuality or remove editorial failures.

The independent `verify-morning-delivery.yml` audit runs at the 08:15 New York scheduled tick. It reads the durable daily ledger for the configured recipient and fails if no confirmed send exists, the timestamp is missing/ambiguous, or acceptance occurred outside 08:00:00–08:01:00 local. It then requires Resend to confirm delivery to the configured recipient. It never sends an email. A late sending workflow can succeed while this timing audit correctly fails. The one-minute tolerance measures provider acceptance, not the precise second the email becomes visible in an inbox. Both EST/EDT and transition dates are tested. Actual future morning success remains unproven until this audit passes on real scheduled delivery.

## Generation latency improvements

The CPU pipeline now saves validated article-level assessments using immutable source identity, publication timestamp, supplied text, model/settings and classification rules. Changing feed order or inserting a new article no longer invalidates every old assessment. Only new/changed inputs are classified on a retry, within the existing four-hour cache TTL; malformed/expired entries are recomputed. Timeliness and send freshness are always recalculated. Grouped-report comparisons use original publication timestamps and reporting rather than the advancing retrieval clock, so unchanged evidence can reuse a comparison while corrected/new reports invalidate it. Cached rejections remain rejections.

Final review retains reasoning but bounds its output to 2,000 tokens instead of 6,000, with the existing one-time structured-output continuation. Instructions distinguish raw Traditional Chinese evidence from Simplified Chinese displayed copy and armed conflict from sanctions/legal enforcement. A specifically identified rejected event can be omitted once, followed by all original count, balance, provenance and freshness gates and a new independent final review. Failure to approve the revised edition still stops sending. No source collection or full classification restart is needed for that repair. The send wait now wakes at the configured target instead of adding up to 30 seconds of polling delay. Model-call durations and reused/new assessment counts are logged without secrets. Recovery ticks check the durable ledger before restoring the model; a sent edition skips expensive startup, while pending/unknown sends still require reconciliation.

The independent timing audit still determines actual morning punctuality. These changes do not remove GitHub scheduling/runner delays, publisher outages or mail-provider latency, and a failed factual review still blocks mail.
