# Reading the sentiment trend chart

A short note on what "Negative sentiment over time" actually shows — and the
mistake it invites.

---

## What the line is

One point per day: **the share of that brand's reviews scored negative**.

Hovering 31 July for Aurora Foods gives `28%`. That is 13 negative reviews out
of 46 that day. Nothing more.

---

## The chart looks volatile. It is not.

Aurora Foods, 90 days, measured:

| | |
|---|---|
| Mean negative rate | **31.1%** |
| Standard deviation | 6.9 points |
| Range | 15.9% – 49.1% |
| Reviews per day | ~49 |

Peaks near 49% next to troughs near 16% look like something happening. Check it
against what randomness alone would produce.

For a proportion `p` measured on `n` samples, the standard error is:

```
√(p(1 − p) / n)  =  √(0.311 × 0.689 / 49)  =  6.6 percentage points
```

**Expected from pure sampling noise: 6.6. Observed: 6.9. Ratio: 1.04.**

Essentially all of the visible movement is the statistical equivalent of
flipping a biased coin 49 times a day and watching the count wobble. Aurora
Foods' underlying negativity did not measurably change across three months.

---

## Why the anomaly detector has three gates

If a human eyeballed this chart, they would report an incident most weeks. The
detector reports **5** negative-sentiment anomalies for Aurora Foods in 90 days,
because an event has to clear all of:

| Gate | Value |
|---|---|
| Minimum volume | 10 reviews |
| Z-score vs 7-day baseline | ≥ 2.0 |
| Percentage change | ≥ 25% |

The z-score gate is doing exactly this arithmetic automatically — comparing a
day against the recent spread rather than against a person's impression of the
line.

---

## How to read it

- **Ignore single spikes.** One day carries roughly ±7 points of noise.
- **Watch the level, not the wiggle.** Is the whole band drifting upward across
  weeks? That is signal.
- **Trust the flagged anomalies.** They have already survived the gates; your
  eyes have not.
- **Fewer reviews means more noise.** A brand with 10 reviews a day has a
  standard error near 15 points, so its line will look wilder while meaning
  less. Volume and volatility are inversely related, always.

---

## The one-line version

> Most of what moves on this chart is sample size, not sentiment.
