"""
Reconciliation Engine.
Matches transactions across sources and identifies discrepancies.
Uses fuzzy matching on date, amount, and description.
"""

import json
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import List, Tuple, Optional, Dict
from collections import defaultdict

from models import (
    UnifiedTransaction, TransactionSource, ReconciliationStatus
)
from config import MATCH_TOLERANCE, DATE_MATCH_WINDOW, AUTO_MATCH_THRESHOLD


class ReconciliationEngine:
    """
    Core reconciliation logic.

    Strategy:
    1. Load transactions from all sources
    2. Group by approximate date + amount
    3. Score potential matches on multiple dimensions
    4. Auto-match high-confidence pairs
    5. Flag conflicts and unmatched for review
    6. Generate upload batch for QuickBooks
    """

    def __init__(self):
        self.all_transactions: List[UnifiedTransaction] = []
        self.matches: List[Tuple[UnifiedTransaction, UnifiedTransaction, float]] = []
        self.unmatched: List[UnifiedTransaction] = []
        self.conflicts: List[Tuple[UnifiedTransaction, List[UnifiedTransaction]]] = []

    def add_transactions(self, transactions: List[UnifiedTransaction]):
        """Add transactions from any source."""
        self.all_transactions.extend(transactions)

    def reconcile(self) -> Dict:
        """
        Run full reconciliation across all loaded transactions.
        Returns a summary dict.
        """
        # Separate by source
        by_source: Dict[TransactionSource, List[UnifiedTransaction]] = defaultdict(list)
        for txn in self.all_transactions:
            by_source[txn.source].append(txn)

        # Get QBO transactions as the baseline (if any)
        qbo_txns = by_source.get(TransactionSource.QUICKBOOKS, [])
        external_txns = []
        for source, txns in by_source.items():
            if source != TransactionSource.QUICKBOOKS:
                external_txns.extend(txns)

        if qbo_txns:
            # Mode 1: Reconcile external sources AGAINST existing QBO data
            self._reconcile_against_qbo(external_txns, qbo_txns)
        else:
            # Mode 2: Cross-reconcile between external sources (detect duplicates)
            self._cross_reconcile(external_txns)

        # Identify what needs to be uploaded to QBO
        to_upload = [
            txn for txn in external_txns
            if txn.recon_status == ReconciliationStatus.UNMATCHED
        ]

        return {
            "total_transactions": len(self.all_transactions),
            "by_source": {s.value: len(t) for s, t in by_source.items()},
            "matched": len(self.matches),
            "unmatched": len(self.unmatched),
            "conflicts": len(self.conflicts),
            "to_upload": len(to_upload),
            "to_upload_amount": sum(t.amount for t in to_upload),
        }

    def _reconcile_against_qbo(
        self,
        external: List[UnifiedTransaction],
        qbo: List[UnifiedTransaction]
    ):
        """Match external transactions against what's already in QuickBooks."""
        # Index QBO transactions by (date_range, approximate_amount)
        qbo_index = self._build_index(qbo)
        used_qbo_ids = set()

        for txn in external:
            candidates = self._find_candidates(txn, qbo_index)
            # Filter out already-matched QBO transactions
            candidates = [(q, s) for q, s in candidates if q.id not in used_qbo_ids]

            if not candidates:
                txn.recon_status = ReconciliationStatus.UNMATCHED
                self.unmatched.append(txn)
                continue

            # Sort by score descending
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_match, best_score = candidates[0]

            if best_score >= AUTO_MATCH_THRESHOLD:
                txn.recon_status = ReconciliationStatus.MATCHED
                txn.matched_txn_id = best_match.id
                txn.match_confidence = best_score
                used_qbo_ids.add(best_match.id)
                self.matches.append((txn, best_match, best_score))
            elif best_score >= 0.5:
                txn.recon_status = ReconciliationStatus.PARTIAL_MATCH
                txn.matched_txn_id = best_match.id
                txn.match_confidence = best_score
                self.conflicts.append((txn, [c[0] for c in candidates[:3]]))
            else:
                txn.recon_status = ReconciliationStatus.UNMATCHED
                self.unmatched.append(txn)

    def _cross_reconcile(self, transactions: List[UnifiedTransaction]):
        """
        When no QBO baseline exists, check for duplicates across sources
        and prepare everything for upload.
        """
        # Group by amount + approximate date to detect cross-source duplicates
        by_amount = defaultdict(list)
        for txn in transactions:
            # Round amount to detect matches
            key = round(txn.amount, 2)
            by_amount[key].append(txn)

        for amount, group in by_amount.items():
            if len(group) == 1:
                # Unique — mark as ready for upload
                group[0].recon_status = ReconciliationStatus.UNMATCHED
                self.unmatched.append(group[0])
                continue

            # Multiple transactions with same amount — check if cross-source duplicates
            sources = set(t.source for t in group)
            if len(sources) == 1:
                # All from same source — likely different transactions
                for txn in group:
                    txn.recon_status = ReconciliationStatus.UNMATCHED
                    self.unmatched.append(txn)
            else:
                # Cross-source — could be the same transaction (e.g., transfer between accounts)
                # Score them pairwise
                matched_ids = set()
                for i, txn_a in enumerate(group):
                    if txn_a.id in matched_ids:
                        continue
                    for txn_b in group[i+1:]:
                        if txn_b.id in matched_ids:
                            continue
                        if txn_a.source == txn_b.source:
                            continue

                        score = self._match_score(txn_a, txn_b)
                        if score >= AUTO_MATCH_THRESHOLD:
                            txn_a.recon_status = ReconciliationStatus.MATCHED
                            txn_b.recon_status = ReconciliationStatus.MATCHED
                            txn_a.matched_txn_id = txn_b.id
                            txn_b.matched_txn_id = txn_a.id
                            txn_a.match_confidence = score
                            txn_b.match_confidence = score
                            matched_ids.add(txn_a.id)
                            matched_ids.add(txn_b.id)
                            self.matches.append((txn_a, txn_b, score))
                            break

                for txn in group:
                    if txn.id not in matched_ids:
                        txn.recon_status = ReconciliationStatus.UNMATCHED
                        self.unmatched.append(txn)

    def _build_index(
        self, transactions: List[UnifiedTransaction]
    ) -> Dict[Tuple[int, int], List[UnifiedTransaction]]:
        """Build a lookup index keyed by (year_month, amount_bucket)."""
        index = defaultdict(list)
        for txn in transactions:
            year_month = txn.date.year * 100 + txn.date.month
            # Bucket amounts to nearest dollar for fast lookup
            amount_bucket = int(round(txn.amount))
            # Also add adjacent buckets for tolerance
            for bucket in [amount_bucket - 1, amount_bucket, amount_bucket + 1]:
                index[(year_month, bucket)].append(txn)
        return index

    def _find_candidates(
        self,
        txn: UnifiedTransaction,
        index: Dict
    ) -> List[Tuple[UnifiedTransaction, float]]:
        """Find potential matches from the index."""
        year_month = txn.date.year * 100 + txn.date.month
        amount_bucket = int(round(txn.amount))

        # Look in current and adjacent months
        candidates = []
        for ym in [year_month - 1, year_month, year_month + 1]:
            for bucket in [amount_bucket - 1, amount_bucket, amount_bucket + 1]:
                for candidate in index.get((ym, bucket), []):
                    score = self._match_score(txn, candidate)
                    if score > 0.3:
                        candidates.append((candidate, score))

        return candidates

    def _match_score(self, a: UnifiedTransaction, b: UnifiedTransaction) -> float:
        """
        Score how likely two transactions are the same.
        Returns 0.0 (no match) to 1.0 (perfect match).
        """
        scores = []

        # Amount match (most important) — weight: 40%
        if abs(a.amount - b.amount) <= MATCH_TOLERANCE:
            scores.append(('amount', 1.0, 0.40))
        elif abs(a.amount - b.amount) <= 1.0:
            scores.append(('amount', 0.8, 0.40))
        elif abs(a.amount - b.amount) <= 5.0:
            scores.append(('amount', 0.4, 0.40))
        else:
            # Amounts too different
            return 0.0

        # Date match — weight: 30%
        day_diff = abs((a.date - b.date).days)
        if day_diff == 0:
            scores.append(('date', 1.0, 0.30))
        elif day_diff <= 1:
            scores.append(('date', 0.9, 0.30))
        elif day_diff <= DATE_MATCH_WINDOW:
            scores.append(('date', 0.7 - (day_diff * 0.1), 0.30))
        else:
            scores.append(('date', 0.0, 0.30))

        # Description similarity — weight: 20%
        desc_score = SequenceMatcher(
            None,
            a.description.lower()[:100],
            b.description.lower()[:100]
        ).ratio()
        scores.append(('description', desc_score, 0.20))

        # Payee match — weight: 10%
        if a.payee and b.payee:
            payee_score = SequenceMatcher(
                None,
                a.payee.lower(),
                b.payee.lower()
            ).ratio()
            scores.append(('payee', payee_score, 0.10))
        else:
            scores.append(('payee', 0.5, 0.10))

        # Weighted sum
        total = sum(score * weight for _, score, weight in scores)
        return round(total, 3)

    def get_upload_batch(self) -> List[UnifiedTransaction]:
        """Get transactions that should be uploaded to QuickBooks."""
        return [
            txn for txn in self.all_transactions
            if txn.source != TransactionSource.QUICKBOOKS
            and txn.recon_status == ReconciliationStatus.UNMATCHED
        ]

    def get_review_batch(self) -> List[Tuple[UnifiedTransaction, List[UnifiedTransaction]]]:
        """Get transactions that need human review."""
        return self.conflicts

    def generate_report(self) -> str:
        """Generate a human-readable reconciliation report."""
        lines = []
        lines.append("=" * 70)
        lines.append("RECONCILIATION REPORT")
        lines.append("=" * 70)
        lines.append("")

        # Summary
        by_source = defaultdict(list)
        for txn in self.all_transactions:
            by_source[txn.source.value].append(txn)

        lines.append("SOURCE SUMMARY:")
        for source, txns in by_source.items():
            total = sum(t.amount for t in txns)
            lines.append(f"  {source:20s}: {len(txns):5d} transactions  |  Net: ${total:>12,.2f}")

        lines.append("")
        lines.append(f"MATCHES:     {len(self.matches)}")
        lines.append(f"UNMATCHED:   {len(self.unmatched)}")
        lines.append(f"CONFLICTS:   {len(self.conflicts)}")

        # Unmatched details
        if self.unmatched:
            lines.append("")
            lines.append("-" * 70)
            lines.append("UNMATCHED TRANSACTIONS (to upload to QBO):")
            lines.append("-" * 70)
            for txn in sorted(self.unmatched, key=lambda t: t.date):
                lines.append(
                    f"  {txn.date}  {txn.source.value:6s}  "
                    f"${txn.amount:>10,.2f}  {txn.description[:45]}"
                )

        # Conflicts
        if self.conflicts:
            lines.append("")
            lines.append("-" * 70)
            lines.append("CONFLICTS (need review):")
            lines.append("-" * 70)
            for txn, candidates in self.conflicts:
                lines.append(
                    f"  {txn.date}  {txn.source.value:6s}  "
                    f"${txn.amount:>10,.2f}  {txn.description[:45]}"
                )
                for c in candidates:
                    lines.append(
                        f"    → possible: {c.date}  {c.source.value:6s}  "
                        f"${c.amount:>10,.2f}  {c.description[:35]}"
                    )

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_json(self) -> str:
        """Export reconciliation results as JSON."""
        return json.dumps({
            "matches": [
                {
                    "txn_a": a.to_dict(),
                    "txn_b": b.to_dict(),
                    "score": score
                }
                for a, b, score in self.matches
            ],
            "unmatched": [t.to_dict() for t in self.unmatched],
            "conflicts": [
                {
                    "transaction": txn.to_dict(),
                    "candidates": [c.to_dict() for c in cands]
                }
                for txn, cands in self.conflicts
            ],
        }, indent=2, default=str)
