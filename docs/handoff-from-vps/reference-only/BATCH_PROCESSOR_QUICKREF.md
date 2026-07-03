# BATCH PROCESSOR - QUICK REFERENCE
## PR Firm Texas - Production Extraction Process

**Script:** `batch_processor.py`  
**Location:** `projects/PR_Firm_Texas/batch_processor.py`  
**Version:** 1.0  
**Status:** LOCKED - This is THE process

---

## ONE-LINE USAGE

```bash
cd /home/ubuntu/.openclaw/workspace/projects/PR_Firm_Texas
python3 batch_processor.py --input <CSV_FILE> --output <PREFIX>
```

---

## INPUT REQUIREMENTS

### CSV Format
- Must have column: `CONFERENCE URL` (or `conference_url` or `url`)
- Optional: `CONFERENCE` or `conference_name` or `name`

### Example Input
```csv
CONFERENCE,CONFERENCE URL,LOCATION
ABLC 2026,https://ablcevents.com/ablc/,Washington DC
Decarb UK,https://decarbconnectuk.com/,London
```

---

## OUTPUT FILES (3 Generated)

| File | Description |
|------|-------------|
| `{PREFIX}_CONFERENCES_54COLUMNS.csv` | 54-column extraction data |
| `{PREFIX}_EXECUTIVE_REPORT.txt` | Plain text intelligence report |
| `{PREFIX}_results.json` | Raw extraction results |

### Example
```
Input:  conferences.csv
Output: BATCH3

Generates:
- BATCH3_CONFERENCES_54COLUMNS.csv
- BATCH3_EXECUTIVE_REPORT.txt
- BATCH3_results.json
```

---

## WHAT THE SCRIPT DOES

1. **Reads CSV** - Finds CONFERENCE URL column
2. **Extracts** - Crawls each website with LLM extraction
3. **Calculates** - 54-column format with metrics
4. **Categorizes** - 4-tier date validation
5. **Generates** - CSV + JSON + Report
6. **Summary** - Prints completion stats

---

## PROCESS IS NOW LOCKED

**No more manual scripts.** No more inline code.

This script handles:
- ✅ URL extraction from source CSV
- ✅ 54-column output (with metrics column 54)
- ✅ conf_page_url population (Column A)
- ✅ 4-tier categorization
- ✅ Executive report generation
- ✅ Error handling for failed extractions

---

## EMAIL DELIVERY

After running script, email the report:

```python
# Use email_sender.py or manual send
python3 email_sender.py --report BATCH3_EXECUTIVE_REPORT.txt
```

Or: Attach files manually to email.

---

## EXAMPLE SESSION

```bash
# 1. Receive CSV from Matt via email
# 2. Download to: media/inbound/conferences.csv

# 3. Run processor
cd projects/PR_Firm_Texas
python3 batch_processor.py \
    --input media/inbound/conferences.csv \
    --output BATCH3

# 4. Email results
python3 email_sender.py --report BATCH3_EXECUTIVE_REPORT.txt \
    --csv BATCH3_CONFERENCES_54COLUMNS.csv

# 5. Update MASTER_TRACKING.md with completion
```

---

## TROUBLESHOOTING

| Issue | Solution |
|-------|----------|
| "No conferences found" | Check CSV has 'CONFERENCE URL' column |
| Extraction timeout | Script auto-retries once per conference |
| Column count wrong | Verify using `head -1 file.csv | tr ',' '\n' | wc -l` |
| Missing metrics | Should be 54 columns (53 data + 1 metrics) |

---

## DEPENDENCIES

```bash
pip install crawl4ai
```

Already installed on server.

---

*This is THE locked process. Do not modify without approval.*
*Version: 1.0 | Locked: March 7, 2026*
