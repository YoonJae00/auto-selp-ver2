---
title: "KIPRIS API Cost Optimization via LLM Suspect Tagging"
date: "2026-05-19"
category: "docs/solutions/architecture-patterns"
module: "processor"
problem_type: "architecture_pattern"
component: "service_object"
severity: "high"
applies_when:
  - "When an external API has strict rate limits (e.g., KIPRIS 1000/month)"
  - "When LLM can reliably estimate the probability of needing the API call"
tags: ["kipris", "cost-optimization", "llm-filtering", "failover"]
---

# KIPRIS API Cost Optimization via LLM Suspect Tagging

## Context
The application needs to verify if product keywords are registered trademarks to prevent copyright issues. Initially, the system sent every generated keyword to the KIPRIS API for verification. With KIPRIS having a strict limit of 1,000 calls per month, processing thousands of products could exhaust the quota within hours.

## Guidance
Instead of verifying every keyword, use the LLM to pre-filter and classify keywords into "safe" (e.g., generic nouns) or "brand_suspected".
1. Only call the expensive external API (KIPRIS) on the `brand_suspected` keywords.
2. Implement a user-configurable toggle to entirely disable the external API call (`kiprisEnabled = false`).
3. When the API is disabled (or quota exhausted), use the LLM's `brand_suspected` classification as a "failover" mechanism—automatically excluding those keywords and returning them as `llm_suspected` warnings instead of verified KIPRIS hits.

```python
# Before: Calling API for every keyword
safe_keywords = []
for kw in keywords:
    if check_kipris(kw): # Expensive!
        safe_keywords.append(kw)

# After: LLM filtering + Fallback
# Step 1: LLM batch classification
suspects = llm.classify(keywords) 

# Step 2: Conditional API call
if kipris_enabled:
    for kw in suspects:
        if check_kipris(kw):
            warnings.append(kipris_confirmed)
else:
    # Failover: exclude suspects entirely without calling API
    for kw in suspects:
         warnings.append(llm_suspected)
```

## Why This Matters
- **Cost Reduction**: Reduces KIPRIS API calls by over 99% (from 20 per product to ~0.2 per product).
- **Graceful Degradation**: Users can still process products safely even if their KIPRIS API quota runs out, by relying on the LLM's conservative suspect filtering.
- **Transparency**: The UI can distinctively show which removals were confirmed by the authority (KIPRIS) versus which were LLM guesses, allowing users to manually verify the LLM's guesses via direct links.

## When to Apply
- When integrating paid or heavily rate-limited third-party APIs.
- When LLM inference is cheaper and faster than the exact verification API.
- When false positives (removing a safe keyword) are acceptable compared to the risk of false negatives (including a trademarked keyword).

## Examples
If the user uploads keywords: `['가스 쇼바', '무보링 댐퍼', '다이슨', '3BOSS']`
1. The static blacklist instantly removes `다이슨`.
2. The LLM identifies `가스 쇼바` and `무보링 댐퍼` as generic, and `3BOSS` as `brand_suspected`.
3. If `kiprisEnabled` is `false`, the API is never called. `3BOSS` is excluded and flagged as an LLM warning, while generic nouns pass through safely.

## Related
- Frontend UI handling of multiple warning types (`TrademarkModal.tsx`)
- Task pipeline parameter passing (`process_excel_task` in `tasks.py`)
