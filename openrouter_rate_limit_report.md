# OpenRouter Rate Limiting: Incident Report & Analysis

**Date:** 2026-04-13  
**Model affected:** `google/gemini-2.5-flash-image`  
**Error code:** 429 (Too Many Requests)

---

## What Happened

During a live speech-to-speech session, the app successfully made one image edit call, then a second call to the same model (`edit_image`) failed with a 429 rate limit error. The full raw error from OpenRouter:

```
google/gemini-2.5-flash-image is temporarily rate-limited upstream.
Please retry shortly, or add your own key to accumulate your rate limits:
https://openrouter.ai/settings/integrations
```

The app caught this as an `HTTPError` and surfaced it to the agent, which correctly told the user to retry. However, the error metadata was severely stripped compared to a successful response.

---

## The BYOK Smoking Gun

Every request to OpenRouter includes a field in the response metadata:

```json
"is_byok": false
```

**BYOK = Bring Your Own Key.** When `is_byok` is `false`, OpenRouter is routing your request through **their own shared API keys** at the upstream provider — in this case, Google. You are not the only user drawing from that key. Every OpenRouter customer hitting the same model is draining the same rate limit bucket simultaneously.

---

## How OpenRouter's Key Sharing Works

OpenRouter operates as a meta-router: you pay them, and they forward your requests to providers (Google, Anthropic, OpenAI, etc.) using keys they control. This is a **shared hosting model**:

```
Your App → OpenRouter → [Shared Google API Key Pool] → Google Gemini API
```

Rate limits at Google are enforced **per API key**, not per end-user. So when OpenRouter's shared key pool hits Google's limit, every paying OpenRouter customer on that model gets a 429 — regardless of how much *they* individually have used it.

### Why a Free Tier Is the Likely Explanation

The error metadata includes:

```json
"provider_name": "Google",
"is_byok": false
```

Google offers API access at multiple tiers. The most telling sign that OpenRouter may be using **free or low-tier Google API keys** for `gemini-2.5-flash-image`:

1. **The model is new and niche.** `gemini-2.5-flash-image` is a specialized image-generation endpoint. OpenRouter likely hasn't invested in high-quota paid keys for it yet — it's cheaper to provision it on a free or low-tier key and let users BYOK if they need reliability.

2. **The rate limit hit almost immediately.** One successful call, then a 429 on the second. This is consistent with very low RPM (requests per minute) limits — the kind you see on free-tier Google AI Studio keys (e.g., 2 RPM on some models).

3. **The error says "temporarily rate-limited upstream."** The word "temporarily" and the suggestion to "retry shortly" is consistent with a short rolling window (e.g., 1 minute) exhausted — exactly what a free-tier key looks like under any meaningful shared load.

4. **No failover occurred.** A properly resourced key pool would round-robin across multiple keys on a 429. The fact that the error surfaced to you at all strongly suggests they either have **one key** for this model, or all their keys for it are on the same low-quota tier.

---

## What's Missing From the Failed Response

Comparing a successful call vs. the 429 failure:

| Field | Success | Failure |
|---|---|---|
| `generation_id` | ✅ Present | ❌ Missing |
| `endpoint_id` | ✅ Present | ❌ Missing |
| `provider_responses[]` | ✅ Full array | ❌ Missing |
| `usage` / cost data | ✅ Present | ❌ Missing |
| `is_byok` | ✅ Present | ⚠️ Only in error metadata |

The absence of `generation_id` means you cannot look up the failed request in OpenRouter's dashboard. You have no way to audit how many endpoints they tried, which key failed, or whether any retry logic ran. OpenRouter is hiding the mechanics of the failure.

---

## Why This Has Probably Been Slowing You Down

The shared key problem isn't just about hard 429 errors. Subtler effects include:

- **Increased latency** — When a shared key is under load but not yet rate-limited, requests queue. You experience this as slow responses with no clear cause.
- **Inconsistent throughput** — Your app's performance is coupled to the usage patterns of strangers. Busy periods for other OpenRouter users become busy periods for you.
- **Silent degradation** — Some rate limiting manifests as slower responses rather than outright errors, making it nearly impossible to diagnose without provider-level telemetry.

Any unexplained slowness you've experienced on OpenRouter-routed models is a candidate for shared key contention.

---

## The Fix: BYOK

The solution is straightforward. For every provider you use heavily, add your own API key in OpenRouter's settings:

**https://openrouter.ai/settings/integrations**

| Provider | Get your key at |
|---|---|
| Google (Gemini) | [aistudio.google.com](https://aistudio.google.com) |
| Anthropic (Claude) | [console.anthropic.com](https://console.anthropic.com) |
| OpenAI | [platform.openai.com](https://platform.openai.com) |

Once BYOK is configured for a provider:
- `is_byok` flips to `true` in all response metadata
- Your requests use your own key's quota — fully isolated from other users
- You accumulate your own rate limit budget independently
- Failed requests will include your own key's error context, not OpenRouter's opaque shared pool errors

### What "Accumulate" Means

Rate limits work on a rolling window — your quota refills over time. With a shared key, thousands of users are draining and refilling the same bucket. With your own key, **you are the only one drawing from it**, so the refill actually accrues to you. On high-RPM paid tiers, this means sustained throughput instead of sporadic bursts between throttles.

---

## Key Takeaways

1. **OpenRouter's default is shared keys.** You are not getting dedicated capacity just because you're a paying customer. You're paying for routing convenience, not quota isolation.

2. **`is_byok: false` is a red flag** in any response metadata. It means your request went through their pool.

3. **BYOK is the only way to get reliable throughput** on OpenRouter for production workloads. It should be the first thing configured, not a last resort after hitting 429s.

4. **New/niche models are the most vulnerable.** OpenRouter likely provisions free or low-quota keys for models that aren't heavily used yet, betting that most users won't notice. `gemini-2.5-flash-image` is exactly that kind of model.

5. **Unexplained latency is suspect.** If you've experienced inconsistent response times on OpenRouter-routed models, shared key contention is a likely contributing factor — it just doesn't always manifest as a hard error.

---

## Code Fix Applied

As part of this investigation, a bug was found in `tool_handlers.py` where HTTP error responses were being truncated before logging, hiding the full error detail:

```python
# Before (truncated at 500 / 200 chars)
logging.error(f"HTTP error from OpenRouter: {e.response.status_code} - {e.response.text[:500]}")
return {"error": f"API error {e.response.status_code}: {e.response.text[:200]}"}

# After (5000 / 2000 chars — effectively never truncates for JSON error blobs)
logging.error(f"HTTP error from OpenRouter: {e.response.status_code} - {e.response.text[:5000]}")
return {"error": f"API error {e.response.status_code}: {e.response.text[:2000]}"}
```

This was masking the full OpenRouter error body, making debugging harder than it needed to be.
