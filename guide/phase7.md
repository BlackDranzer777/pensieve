# Phase 7 — The React Dashboard

**Status: complete and verified.** Compiled, linted, unit-tested and loaded
in a browser against a database holding 37,800 transformer-scored reviews.

```
tsc -b --noEmit          clean
eslint --max-warnings 0  clean
vitest                   17 passed
```

---

## What this phase is about

Phases 2–6 turned a messy CSV into indexed PostgreSQL tables behind 18 API
endpoints. All of that is invisible. Phase 7 is where a person can finally
*see* it.

Until now five of the six pages rendered an explicit "not built yet" panel.
They showed no numbers at all, deliberately — a screenshot full of invented
metrics is the easiest lie a portfolio project can tell.

---

## How it relates to Phase 6

Close to one endpoint per page:

| Page | Endpoints |
|---|---|
| Overview | `/overview` |
| Brands | `/brands/comparison`, `/countries` |
| Trends | `/trends/sentiment`, `/trends/topics`, `/anomalies` |
| Reviews | `/reviews`, `/reviews/facets`, `/reviews/{id}` |
| Data quality | `/data-quality`, `/data-quality/trend` |
| Pipeline runs | `/pipeline-runs`, `/pipeline-runs/{id}` |

Because Gold pre-aggregated everything, these are small indexed reads. The
Brands page sums 450 rows, not 37,800.

---

## Zod on every response

Every endpoint has a matching schema in `src/types/`:

```
types/common.ts      the Page envelope
types/analytics.ts   overview, brands, trends, anomalies
types/reviews.ts     the Review Explorer
types/telemetry.ts   runs and quality
```

**Why validate a response you wrote yourself.** The backend is Python and the
frontend is TypeScript; nothing but discipline keeps them in step. Without a
runtime check, a renamed field arrives as `undefined` and surfaces three
components later as "Cannot read properties of undefined" — a stack trace that
points nowhere near the actual cause. With one, the error names the endpoint
and the field.

---

## `null` is not zero

The API returns `null`, not `0`, for a percentage with no denominator. "0% of
no reviews were negative" is not a fact.

So every schema admits `null`, and `MetricTile` renders it as an em dash:

```tsx
{value ?? <span className="text-ink-subtle">—</span>}
```

A reassuring zero where there is no data is exactly the kind of quiet
misinformation a dashboard should not produce.

---

## Filter state lives in the URL

The Review Explorer keeps all seven filters, the search term, and the page
number in the query string rather than in component state.

That costs a little plumbing and buys three things:

- the back button works
- a refresh does not reset the view
- a filtered view can be pasted to a colleague

Which is most of what a review explorer is for.

---

## Decisions worth defending

**One `/overview` request, not six.** The landing page could fetch its KPIs,
sentiment mix, topics, languages, anomalies and run status separately. That
would be six independent chances to hang on a spinner. One endpoint, one
loading state.

**Duplicates hidden by default.** Gold excludes them, so the table would
otherwise disagree with every aggregate on the site — and "the numbers do not
add up" destroys trust faster than any missing feature. The toggle exists
because inspecting them is sometimes the point.

**Charts read colours from CSS variables.** Recharts cannot see Tailwind
classes, so `chart-theme.ts` resolves the same `--color-*` tokens the rest of
the UI uses. Hardcoded hex values would give charts a palette that ignores the
light/dark toggle.

**`connectNulls={false}`.** A missing day stays a gap. Drawing a straight line
through absent data invents a measurement.

**Sentiment and severity have fixed colours** wherever they appear. The same
metric looking different on two pages is a credibility problem, not a styling
one.

**Stable sort tiebreaker.** The reviews query orders by the chosen column *and*
`id`. Without the second key, two reviews sharing a timestamp can swap places
between page 1 and page 2 — one row shown twice, another never shown at all.

---

## Files

| File | Role |
|---|---|
| `src/types/*.ts` | Zod schemas mirroring the API |
| `src/hooks/useAnalytics.ts` | Overview, brands, trends, anomalies |
| `src/hooks/useReviews.ts` | Review search, detail, facets |
| `src/hooks/useTelemetry.ts` | Runs and data quality |
| `src/components/charts/` | Time series, category bars, shared theme |
| `src/components/ui/MetricTile.tsx` | KPI tiles |
| `src/components/ui/Controls.tsx` | Filters, pagination, badges |
| `src/features/*/` | The six pages |

`PhasePlaceholder.tsx` was deleted — with every page built, it was dead code.

---

## Known gaps

- No CSV export on the Review Explorer yet (listed in the plan, not built).
- The Overview's `total_reviews` reports the non-duplicate count, understating
  the dataset by the number of duplicates. Fix pending.

**The two predicted failures both happened**, which is the argument for running
things rather than reasoning about them:

- Recharts 3 types the tooltip value as `ValueType | undefined`, so annotating
  the formatter parameter as `number | string` made the callback unassignable.
  The parameter type is now inferred.
- `<Cell>` is deprecated in Recharts 3. Per-bar colour now rides on the datum
  as `fill`, which Recharts reads directly.

---

## Where this sits

```
Phase 5   Silver   -> Gold          aggregation and anomalies
Phase 6   Gold     -> PostgreSQL    18 endpoints, 434 tests green
Phase 7   API      -> dashboard     six pages, verified   <- you are here
Phase 8   tests, CI, benchmark, docs
```
