#!/bin/bash
cd /c/Users/matts/cfp-monitor
mkdir -p experiments/purpose_audit/narrow_test
echo "start $(date +%T)" > experiments/purpose_audit/narrow_test/progress.txt
python experiments/purpose_audit/narrow_test_run.py > experiments/purpose_audit/narrow_test/summary.txt 2>&1
echo "rc=$? end $(date +%T)" >> experiments/purpose_audit/narrow_test/progress.txt
