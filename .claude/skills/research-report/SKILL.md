---
name: research-report
description: Write the final research report of a paper replication from the lab's own records (specs, reports, audits, MLflow runs), with every number traceable and nothing beyond what the records show.
---

# Research report

The report summarises what was done and found. It never adds new analysis,
and it never reruns anything on the OOS period.

1. **Sources only.** Take every number from a committed report in
   `research/reports/` or a named MLflow run. Cite the file or the run id. If
   a number is not recorded, leave it out or mark it "not recorded".
2. **Structure:**
   - question;
   - paper and hypotheses;
   - data and sample design;
   - methods, with rule classifications;
   - development results;
   - robustness and multiple testing;
   - audits and what they changed;
   - pre-registration;
   - out-of-sample result against it;
   - limitations;
   - reproducibility;
   - conclusion.
3. **Honesty.**
   - Report failed predictions and errata as prominently as successes.
   - A negative result is a result.
   - State power and what a null result does not rule out.
4. **Licensed data.** Aggregates only: no prices, rows or quotes.
5. **Reproducibility.** List the commands, the freeze tags, and
   `uv run python -m quant_lab.reproduce` for the headline numbers.
6. **Location.** Write the report to `research/reports/final_report.md` and
   update `ROADMAP.md`.
