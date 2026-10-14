# Claim Status Tracker

A simple health-insurance claim tracker (Python 3.8+, standard library only).

## Quick start
```bash
python claim_tracker.py demo
python claim_tracker.py list
python claim_tracker.py show CLM-0001
python claim_tracker.py update CLM-0004 RECEIVED --note "Received via EDI"
python claim_tracker.py report
```

## Workflow
SUBMITTED -> RECEIVED -> IN_REVIEW -> PENDED / APPROVED / DENIED -> PAID -> CLOSED
DENIED -> APPEALED -> IN_REVIEW

Edit the `TRANSITIONS` dictionary in `claim_tracker.py` to change the rules.
