"""Docs for ACT-67 follow-up 3 (run once; ASCII)."""
p = r"C:\Users\matts\cfp-monitor-builder17\docs\operations\WEEKEND-PROCESS.md"
s = open(p, encoding="utf-8").read()
anchor = "3. **[Update]** **Adds permanent IDs to the awards list**"
add = ("   **Upstream's reply with award ids (2026-10-12; operator-run, before the Friday research starts):** the research reads each row's permanent id from `Awards_input.csv` WHEN IT RUNS, so ids must be stamped before Friday 02:00. "
       "The reviewed reply is `docs/operations/award_ids_reply_20261012.csv`: 30 NEW awards (stamped as new ids, `stamp_given_ids.py --awards`), 7 rows upstream calls the SAME award as one we hold (`customer_awards.py --relabel` puts DUP_OF back to the survivor, "
       "so the award is researched once and upstream's new id is NOT used), 2 rows upstream calls distinct but we already hold (our EXISTING id is stamped, `--allow-held`), and 2 listed rows (World Hydrogen and Carbon Asia, Clinton Global Initiative) whose ids are stamped. "
       "`customer_awards.py --reply-plan` checks all of it first and changes nothing: an id another row already carries, a row still labelled DUP_OF, a missing survivor or an id not in the database is a PROBLEM. "
       "Their research now returns World Hydrogen and Carbon Asia and Clinton Global Initiative as awards (the Speaking / Registration typing is on OLD carried rows only), so they load as awards under upstream's ids and the old carried row is dropped as superseded "
       "(same name, same market). A researched row typed as anything else than an award is never first-loaded (import_awards would leave it out and the read-back would undo the load); it is named. *(customer_awards.py, stamp_given_ids.py, weekend_import.py)*\n")
assert anchor in s
s = s.replace(anchor, add + anchor, 1)
s = s.replace("- **2026-10-12** - (follow-up 2)", "- **2026-10-12** - (follow-up 3) upstream's reply with 41 award ids: reviewed file, `--reply-plan`, `--relabel`, stamping commands; a carried Speaking/Registration row is superseded by the same listing researched as an award; a non-award row is never first-loaded.\n- **2026-10-12** - (follow-up 2)", 1)
open(p, "w", encoding="utf-8", newline="\n").write(s)

p = r"C:\Users\matts\cfp-monitor-builder17\docs\operations\TOOLING.md"
s = open(p, encoding="utf-8").read()
old = "`--unlabel [--apply [--live]]` (operator-run, ACT-67 follow-up 2)"
assert old in s
s = s.replace(old, "`--reply FILE --reply-plan` (checks upstream's reviewed award-id reply against the list, writes `ids_new.csv` / `ids_existing.csv` for `stamp_given_ids.py --awards [--allow-held]`, changes nothing) and `--reply FILE --relabel [--apply [--live]]` (sets DUP_OF back to the survivor on the rows upstream rules the SAME award; inverse of --unlabel; `write_approved` backup + proof; second apply 0) (ACT-67 follow-up 3; reviewed file `docs/operations/award_ids_reply_20261012.csv`). " + old, 1)
open(p, "w", encoding="utf-8", newline="\n").write(s)

p = r"C:\Users\matts\cfp-monitor-builder17\docs\operations\QA-REGISTER.md"
s = open(p, encoding="utf-8").read()
old = "Un-label (operator-run):"
assert old in s
s = s.replace(old, "Upstream's award-id reply (operator-run): `customer_awards.py --reply FILE --reply-plan`, then `--relabel`, then `stamp_given_ids.py --awards` (new ids) and `--awards --allow-held` (existing ids), each dry run first; a row typed as a non-award is never first-loaded and a carried non-award row is superseded by the same listing researched as an award. " + old, 1)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
