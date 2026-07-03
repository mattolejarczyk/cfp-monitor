# PR Monitor 1 — Step-by-Step Reference Guide

This document explains what happens at each step of the PR Monitor 1 dashboard,
from both the user's perspective (what you see) and the behind-the-scenes perspective
(what the system does). Written in plain language.

---

## Step 1 — Create Prompt

### What you see (user perspective):

You're presented with a form where you define the "search criteria" for the whole
monitoring run:

1. **Market** — A text field where you type the industry or topic you want to
   monitor (e.g. "Hydrogen", "Healthcare", "Legal Tech"). This is the main subject
   the AI will search for.

2. **Record Type** — A dropdown with three options: "both" (conferences AND awards),
   "conference" only, or "award" only. This controls what kind of opportunities
   the system will look for.

3. **Conference Region Scope** — A dropdown that lets you narrow where to look:
   - "US" — only US-based conferences
   - "International" — global, including US
   - "Specific Countries" — pick individual non-US countries from a multi-select list

4. **US Coverage Preset** — When region is US, you can choose:
   - "All US states" (default)
   - "Contiguous US" (lower 48, excludes Alaska and Hawaii)
   - "Custom states" — pick specific states from a multi-select list

5. **Award Geo Preference** — A separate set of dropdowns (country, state, city)
   that lets you set geographic preferences specifically for award searches.

6. Two buttons at the bottom:
   - **"Save Prompt Setup"** — saves your form settings as preferences
   - **"Generate Prompt Pack"** — takes your settings and creates the actual
     search instructions (prompts) that will be sent to AI models in Step 2

After clicking either button, the status text below updates to confirm success or
show an error. After generating a prompt pack, a preview appears showing the
two generated prompts: one for conference discovery and one for award discovery.

### What happens behind the scenes:

**When you click "Save Prompt Setup":**

1. The browser first validates your geo selections (makes sure states/countries
   are consistent with your region scope choice).

2. It collects all your form fields into a JSON package: market, record type,
   region scope, selected states, selected countries, and geo preferences.

3. It sends this package to the backend endpoint `/api/pr-monitor-1/preferences`
   via a POST request.

4. The backend cleans up the data (trims whitespace, normalizes to uppercase),
   adds a timestamp, and writes everything to a `preferences.json` file in your
   project's runtime folder.

5. The status line updates with a one-line summary of what was saved, e.g.:
   "Setup saved | mkt:Hydrogen | type:both | conf:US [ALL] | award:US/--/-"

**When you click "Generate Prompt Pack":**

1. Same geo validation as above.

2. Same data collection into a JSON package.

3. This time it sends to `/api/pr-monitor-1/prompt-pack`.

4. The backend does a lot of validation:
   - Market is required — it will reject with an error if blank
   - Region scope must be US, INTERNATIONAL, or SPECIFIC_COUNTRIES
   - States are only valid when scope is US
   - Countries are only valid when scope is SPECIFIC_COUNTRIES
   - US is not allowed in the countries list (it's handled separately)
   - Award geo preference must be at least 3 characters

5. Based on your selections, it builds a "targeting clause" — a sentence that
   describes the geographic focus. For example:
   - "Conference targeting scope: US only. Restrict to these states: TX, CA."
   - "Conference targeting scope: INTERNATIONAL (global)."

6. It then assembles 5 prompts:
   - **conference_discovery** — Instructions for AI models to find conference
     URLs for your market, with the geographic targeting clause baked in
   - **award_discovery** — Similar instructions for finding award opportunities,
     with your award geo preference and priority mode
   - **url_validation** — Instructions for validating whether found URLs are
     relevant and high-quality
   - **geo_enrichment** — Instructions for extracting location data from pages
   - **output_standardization** — Instructions for formatting results consistently

7. The prompt pack is saved as a JSON file with a unique ID (based on the
   current timestamp) and a schema version tag.

8. The browser displays a preview showing the conference and award discovery
   prompts in scrollable boxes, with pill badges showing the market, record
   type, and schema version.

---

## Step 2 — Discover URLs

### What you see (user perspective):

1. A single button: **"Discover URLs (3 Models)"**

2. When you click it, a browser confirmation popup appears:
   "Confirm deep research run? This may incur API costs." You click OK or Cancel.

3. The status text changes to: "Running multi-model live discovery..."

4. After completion (usually a few minutes), the status updates to something like:
   "Multi-model live run saved: job_abc123"

5. A results panel appears below with three sections:
   - **Provider Results table** — Shows Perplexity, ChatGPT, and Gemini as rows,
     with columns for how many conference URLs, award URLs, and total URLs each
     found.
   - **Pairwise Overlap table** — Shows which pairs of models found the same
     URLs (e.g. "perplexity + chatgpt → 12 shared URLs"). This tells you how
     much agreement there was between models.
   - **Master URL List** — A table of the first 25 combined URLs, showing the
     link, whether it's a conference or award, which models found it (e.g.
     "chatgpt, perplexity"), a confidence score, and whether it was found by
     multiple models ("deduped_multi_source") or just one ("single_source").

### What happens behind the scenes:

1. **Collects your settings** — Reads the market, geo preferences, and record
   type from the form fields you filled in Step 1.

2. **Generates a prompt pack first** — Internally calls the same prompt-pack
   logic from Step 1, saving the prompts to your project folder. This ensures
   the discovery uses your latest settings.

3. **Sends prompts to 3 AI models simultaneously** — Perplexity, ChatGPT, and
   Gemini each receive the conference discovery prompt and the award discovery
   prompt. They independently search the web and return lists of URLs they found.
   If you're in dry-run mode (testing), it uses fake results instead of actually
   calling the APIs.

4. **Each model returns structured results** — Each one sends back a list of
   conference URLs and award URLs, with titles.

5. **Merges and deduplicates** — The system normalizes all URLs (so slight
   variations of the same link count as one). It combines results from all 3
   models. If the same URL was found by multiple models, it gets a higher
   confidence score. The scoring is simple: each model that found it adds 0.34
   to the confidence (capped at 1.0). So a URL found by all 3 models gets
   confidence 1.0; found by 2 models → 0.68; found by 1 → 0.34.

6. **Tags each URL** — URLs found by multiple models are tagged
   "deduped_multi_source" (more trustworthy). URLs found by only one model are
   tagged "single_source" (less certain).

7. **Calculates overlap** — It compares which models found the same URLs as each
   other, producing the pairwise overlap counts you see in the UI.

8. **Saves the master list** — The combined, deduplicated list of all URLs is
   saved as a file in your project folder. This becomes the "master list" that
   Step 3 (Crawl) will use.

9. **Returns everything to the browser** — The UI renders the three tables.

**Key idea:** Running 3 models instead of 1 gives you a "wisdom of crowds"
effect. URLs found by multiple independent models are more likely to be real
and relevant. The overlap table helps you gauge how much agreement there was.

---

## Step 3 — Crawl URLs

### What you see (user perspective):

1. A **"Custom URLs"** text box where you can optionally paste specific URLs
   to crawl instead of using the master list. A note below explains: "If this
   box has URLs, Step 3 uses these first and bypasses master-list fallback."

2. A checkbox: **"Use latest master list if URL box is empty"** — checked by
   default. This means if you don't paste custom URLs, it will crawl the
   master list that Step 2 generated.

3. A button: **"Step 3: Crawl URLs"**

4. When clicked, the status shows: "Queueing crawl..." then updates with
   progress percentage as it runs.

5. On completion, you see:
   - Crawl ID, total URL count, and how many were reachable
   - Whether the crawl engine or fallback mode was used
   - An artifacts directory path
   - Engine metrics (total runs, engine runs, fallback runs, failures)
   - Clickable links to the artifact folder and crawl manifest file

6. If the crawl engine fails, a red alert banner appears at the top of the page.

### What happens behind the scenes:

1. **Determines the URL source** — Checks if you pasted custom URLs. If yes,
   those are used. If no, and "use master list" is checked, it loads the master
   list file that Step 2 saved. If neither is available, it returns an error.

2. **Starts an async crawl job** — The crawl runs in the background as a
   separate job (so the browser doesn't freeze). A job ID is returned
   immediately.

3. **The browser polls for progress** — Every few seconds, the browser asks
   the backend "how's job X doing?" and updates the status text with the
   current progress percentage.

4. **The crawl engine visits each URL** — It tries to fetch the web page
   content for each URL. It first tries the primary crawl engine (crawl4ai).
   If that fails, it falls back to a simpler method. Each URL is marked as
   reachable or not.

5. **Saves crawl artifacts** — The results are saved to an artifacts folder:
   - A manifest JSON file listing all URLs and their status
   - The raw content fetched from each URL

6. **Tracks engine metrics** — The system keeps a running count of how many
   crawls used the engine vs. fallback, and how many failures occurred. These
   are displayed in the metrics line and used for the alert banner.

7. **On completion** — The browser displays the results and provides links
   to inspect the raw crawl data.

---

## Step 4 — Extract Data

### What you see (user perspective):

1. **Extraction Mode** dropdown — Two options:
   - "full_ai" — every URL is processed by the AI (slower, more thorough)
   - "smart_hybrid" (default) — a mix of AI and rule-based extraction

2. **Min Confidence** — A number field (default 0.85). This is the minimum
   confidence score the extractor needs to accept a result. Higher = stricter.

3. **"Skip same-day reprocess"** checkbox — If checked, URLs that were already
   processed today won't be re-extracted (saves time and API costs).

4. **"Use latest crawl artifacts if URL box is empty"** — If no custom URLs
   are provided, it uses the crawl results from Step 3.

5. A button: **"Step 4: Extract Data"**

6. When clicked, status shows: "Running extraction... mode=smart_hybrid,
   min_confidence=0.85" then updates with progress.

7. On completion:
   - Extract ID and source crawl ID
   - Linkage info showing which crawl this extraction came from
   - Clickable links to: trace JSON, output CSV, and output report
   - The "Latest Results" table auto-refreshes with metrics (rows scanned,
     updated, flagged, skipped, AI calls, total AI cost)

### What happens behind the scenes:

1. **Determines the URL source** — Same logic as Step 3: custom URLs first,
   then latest crawl artifacts, then master list.

2. **Starts an async extraction job** — Like crawling, extraction runs in the
   background. A job ID is returned immediately.

3. **The browser polls for progress** — Same polling pattern as Step 3.

4. **For each URL, the system:**
   - Fetches the page content (from crawl artifacts or live)
   - Depending on mode, either sends it to the AI or uses rule-based extraction
   - The AI/rule engine looks for: conference name, dates, location, CFP
     (call for papers) status, deadlines, award categories, etc.
   - Each extracted field gets a confidence score
   - Results below your min_confidence threshold are flagged, not discarded

5. **Skips same-day reprocess** — If a URL was already extracted today and
   "skip same-day" is checked, it's skipped entirely.

6. **Saves extraction artifacts:**
   - Trace JSON — a detailed log of what was extracted from each URL
   - Output CSV — the structured data in spreadsheet format
   - Output report — a human-readable summary

7. **Updates the database** — Extracted records are saved to the SQLite
   database, where they'll appear in Step 6 for review.

8. **Auto-refreshes the UI** — After completion, the browser automatically
   reloads the latest results table, run history, and run rows.

---

## Step 5 — Enrich Data

### What you see (user perspective):

1. **"Run to Enrich"** text field — You can paste a specific run ID, or leave
   it empty to enrich the latest run.

2. **"Enrichment Types"** multi-select — Currently one option: "geo" (city,
   state, country from location data). Pre-selected by default.

3. A button: **"Step 5: Enrich Data"**

4. When clicked, status shows: "Running enrichment... types=geo"

5. On completion, status shows: "Enrichment completed: enriched 45 rows,
   120 total with geo"

### What happens behind the scenes:

1. **Finds the run to enrich** — Uses the run ID you provided, or looks up the
   most recent run from the database.

2. **Runs synchronously** — Unlike crawl and extract, enrichment runs in the
   foreground (not async). The browser waits for it to finish.

3. **For each row in the run:**
   - Looks at the location data that was extracted in Step 4
   - Tries to determine the city, state, and country
   - Sets a geo confidence status: GEO_CONFIRMED (clear location found),
     GEO_PARTIAL (some location info found), or GEO_UNKNOWN (no location info)

4. **Updates the database** — The geo fields are written back to each row.

5. **Auto-refreshes the UI** — Same as Step 4: reloads latest results, run
   history, and run rows.

**Note:** Enrichment is a synchronous (blocking) operation, so the browser
waits for it to complete. This is different from Steps 3 and 4 which run
in the background.

---

## Step 6 — Extracted Data Review

### What you see (user perspective):

This is the most complex step — it's where you review and act on the extracted
data. It's a full review workspace with:

**Run Selection:**
1. A **"Paste run_id"** field and **"Use This Run ID"** button — to load a
   specific run.
2. A **run history** section that auto-loads recent runs you can pick from.

**Filter Controls (to narrow down what you see):**
- QA Status (pending / needs_review / ready)
- AI Called (Yes / No)
- Review Status (needs_review / reviewed / follow_up)
- Geo City / State / Country contains
- Domain contains
- Market (multi-select dropdown, populated from your data)
- CFP Status (Unknown / Open / Closed / Empty)
- Checkboxes: Changed only, Has CFP/Deadline, Upcoming only, Exclude past CFP,
  Exclude N/A CFP Deadline, Exclude N/A Conf Dates

**Preset filter buttons:**
- "Needs Review" — shows only rows needing review
- "Follow Up" — shows only follow-up items
- "Reviewed" — shows only reviewed items
- "Reset Filters" — clears all filters

**Action buttons:**
- "Load Selected Run Rows" — loads rows from the selected run
- "Load Market/Customer Latest" — loads the latest portfolio view
- "Export Market CSV" — downloads the current view as a CSV file

**The Data Table:**
A dense 16-column table showing:
Market | Domain | URL | QA | Review | Action | AI | CFP Status |
CFP Deadline | Conf Dates | Geo City | Geo State | Geo Country |
Geo Confid | Flags | Details

- **QA column** shows single characters: `-` (pending), `R` (ready), `!` (needs_review)
- **Review column** shows the current review status
- **Action column** has three buttons per row: "Reviewed", "Defer", "Re-open"
  - "Reviewed" marks the row as reviewed (records your name and timestamp)
  - "Defer" marks it for follow-up later
  - "Re-open" resets it back to needs_review
  - The Re-open button is hidden when the row is already in needs_review status
- **Details column** lets you expand a row to see and edit override fields:
  CFP status, CFP deadline, conference dates, review notes, submission status

**Review Summary:**
Shows counts: "Needs Review: 12 | Reviewed: 45 | Follow Up: 3"

### What happens behind the scenes:

**Loading rows:**
1. When you click "Load Selected Run Rows", the browser sends a request to
   `/api/pr-monitor-1/run/{run_id}/rows` with all your current filter settings
   as query parameters.

2. The backend queries the database for rows matching the run ID and filters,
   and returns them as JSON.

3. The browser stores the rows in memory and renders them in the table.

**Applying filters:**
- All filtering happens in the browser (not on the server). Once rows are
  loaded, checking/unchecking filters instantly shows/hides rows without
  any server requests.
- The Market dropdown is automatically populated from the unique market
  values in your loaded data.

**Review actions (Reviewed / Defer / Re-open):**
1. When you click one of the action buttons, the browser sends a POST to
   `/api/pr-monitor-1-review/review/upsert` with:
   - The event key (unique ID for that row)
   - The market and customer
   - The new status (reviewed / follow_up / needs_review)
   - Your name (from the "Reviewed By" field, defaults to "web_user")

2. The backend updates the review status in the database and records who
   made the change and when.

3. The browser updates the row's status in memory and re-renders the table
   so you see the change immediately.

**Saving overrides:**
1. When you expand a row's details and edit the override fields (CFP status,
   deadline, dates, notes, submission status), then save, the same
   `/api/pr-monitor-1-review/review/upsert` endpoint is called with the
   override data.

2. The backend saves these as overrides on top of the extracted data.
   The original extracted data is preserved; overrides are stored separately.

**Exporting CSV:**
1. Clicking "Export Market CSV" sends a request to
   `/api/pr-monitor-1-review/portfolio/export-csv` with your current filters.

2. The backend generates a CSV file with headers and returns it as a
   downloadable file.

---

## Summary: The Full Pipeline

| Step | What you do | What the system does | Async? |
|------|------------|---------------------|--------|
| 1a | Fill form, click "Save Prompt Setup" | Saves preferences to JSON file | No |
| 1b | Click "Generate Prompt Pack" | Builds 5 AI prompts from your settings, saves to file | No |
| 2 | Click "Discover URLs" | Sends prompts to 3 AI models, merges results, saves master URL list | Yes |
| 3 | Click "Crawl URLs" | Visits each URL, fetches page content, saves crawl artifacts | Yes |
| 4 | Click "Extract Data" | Extracts structured data (dates, location, CFP, etc.) from each page | Yes |
| 5 | Click "Enrich Data" | Adds geo location data (city, state, country) to extracted rows | No |
| 6 | Review, filter, mark rows | Saves your review decisions and overrides to the database | No |

Steps 3 and 4 are async (run in the background with progress polling) because
they can take a long time. Steps 1, 5, and 6 are synchronous (you wait for
them to finish).

The data flows: Prompts → URLs → Crawled Pages → Extracted Data → Enriched Data → Human Review
