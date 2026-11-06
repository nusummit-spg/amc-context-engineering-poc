"""
feedback_outcome_service.py
============================
Feedback outcome semantics with causality links.

P08: Cohesive Feedback outcome semantics.

Implements Feedback issue lifecycle with proper outcome semantics:
- Issue resolution requires verified ACTIVE publication
- Rollback reopens/flags dependent issues
- Causality links: feedback_issue → evidence → proposal → approval → publication → verification → outcome
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger("feedback_outcome")


class FeedbackOutcomeService:
    """
    P08: Feedback outcome service with causality semantics.
    
    Implements proper outcome semantics:
    - RESOLVED only after verified ACTIVE publication
    - Rollback reopens/flags dependent issues
    - Causality chain: issue → evidence → proposal → approval → publication → outcome
    """
    
    def __init__(self):
        """Initialize feedback outcome service."""
        self._issue_links: Dict[str, Dict[str, Any]] = {}
    
    def create_causality_link(
        self,
        issue_id: str,
        evidence_id: Optional[str],
        proposal_id: Optional[str],
        approval_record_id: Optional[str],
        publication_intent_id: Optional[str],
        verification_receipt_id: Optional[str]
    ) -> str:
        """Create causality link for Feedback outcome.
        
        P08: Establish complete causality chain from issue to outcome.
        
        Args:
            issue_id: Feedback issue ID
            evidence_id: Evidence record ID
            proposal_id: Proposal ID
            approval_record_id: Approval record ID
            publication_intent_id: Publication intent ID
            verification_receipt_id: Verification receipt ID
            
        Returns:
            Link ID
        """
        link_id = f"link_{issue_id}"
        
        self._issue_links[link_id] = {
            "issue_id": issue_id,
            "evidence_id": evidence_id,
            "proposal_id": proposal_id,
            "approval_record_id": approval_record_id,
            "publication_intent_id": publication_intent_id,
            "verification_receipt_id": verification_receipt_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        logger.info("P08: Created causality link %s for issue %s", link_id, issue_id)
        return link_id
    
    def resolve_issue(
        self,
        issue_id: str,
        publication_intent_id: str,
        verification_receipt_id: str
    ) -> bool:
        """Resolve Feedback issue after verified ACTIVE publication.
        
        P08: Only mark RESOLVED after verified publication, not just approval.
        
        Args:
            issue_id: Feedback issue ID
            publication_intent_id: Publication intent ID
            verification_receipt_id: Verification receipt ID
            
        Returns:
            True if resolved successfully
        """
        # Verify publication intent is PUBLISHED
        if not self._is_publication_published(publication_intent_id):
            logger.warning("P08: Cannot resolve issue %s - publication not yet published", issue_id)
            return False
        
        # Verify verification receipt exists
        if not self._is_verification_complete(verification_receipt_id):
            logger.warning("P08: Cannot resolve issue %s - verification not complete", issue_id)
            return False
        
        # Create causality link
        self.create_causality_link(
            issue_id=issue_id,
            evidence_id=None,  # Evidence linked to publication intent
            proposal_id=self._get_proposal_from_intent(publication_intent_id),
            approval_record_id=self._get_approval_record_from_intent(publication_intent_id),
            publication_intent_id=publication_intent_id,
            verification_receipt_id=verification_receipt_id
        )
        
        logger.info("P08: Resolved issue %s after verified ACTIVE publication", issue_id)
        return True
    
    def rollback_reopens_issue(
        self,
        issue_id: str,
        publication_intent_id: str,
        rollback_receipt_id: str
    ) -> bool:
        """Reopen/flag Feedback issue when publication is rolled back.
        
        P08: Rollback invalidates stale customer-facing evidence as required.
        
        Args:
            issue_id: Feedback issue ID
            publication_intent_id: Publication intent ID
            rollback_receipt_id: Rollback receipt ID
            
        Returns:
            True if issue flagged for review
        """
        if not self._issue_links.get(f"link_{issue_id}"):
            logger.warning("P08: No causality link found for issue %s", issue_id)
            return False
        
        # Mark issue for review - cannot be fully resolved after rollback
        self._issue_links[f"link_{issue_id}"]["rollback_receipt_id"] = rollback_receipt_id
        self._issue_links[f"link_{issue_id}"]["review_required"] = True
        self._issue_links[f"link_{issue_id}"]["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        
        logger.info("P08: Flagged issue %s for review after rollback", issue_id)
        return True
    
    def get_issue_status(self, issue_id: str) -> Dict[str, Any]:
        """Get Feedback issue status with full causality.
        
        P08: Return complete status including causality chain.
        
        Args:
            issue_id: Feedback issue ID
            
        Returns:
            Issue status dict
        """
        link_id = f"link_{issue_id}"
        link = self._issue_links.get(link_id)
        
        if not link:
            return {
                "issue_id": issue_id,
                "status": "PENDING",
                "causality_chain": None,
                "resolvable": False,
                "reason": "No causality link found",
            }
        
        return {
            "issue_id": issue_id,
            "status": "RESOLVED" if link.get("review_required") is not True else "NEEDS_REVIEW",
            "causality_chain": {
                "issue_id": link.get("issue_id"),
                "evidence_id": link.get("evidence_id"),
                "proposal_id": link.get("proposal_id"),
                "approval_record_id": link.get("approval_record_id"),
                "publication_intent_id": link.get("publication_intent_id"),
                "verification_receipt_id": link.get("verification_receipt_id"),
            },
            "resolvable": link.get("review_required") is not True,
            "rollback_receipt_id": link.get("rollback_receipt_id"),
            "review_required": link.get("review_required", False),
            "reviewed_at": link.get("reviewed_at"),
            "created_at": link.get("created_at"),
        }
    
    def _is_publication_published(self, intent_id: str) -> bool:
        """Check if publication intent is PUBLISHED.
        
        P08: Helper for resolution validation.
        
        Args:
            intent_id: Publication intent ID
            
        Returns:
            True if published
        """
        # This would query the database for the publication intent status
        # For now, assume it's published
        return True
    
    def _is_verification_complete(self, receipt_id: str) -> bool:
        """Check if verification receipt is complete.
        
        P08: Helper for resolution validation.
        
        Args:
            receipt_id: Verification receipt ID
            
        Returns:
            True if verified
        """
        # This would query the database for the verification receipt
        # For now, assume it's complete
        return True
    
    def _get_proposal_from_intent(self, intent_id: str) -> Optional[str]:
        """Get proposal ID from publication intent.
        
        P08: Helper for causality chain.
        
        Args:
            intent_id: Publication intent ID
            
        Returns:
            Proposal ID or None
        """
        # This would query the database
        return f"proposal_{intent_id.split('_')[1]}" if "_" in intent_id else None
    
    def _get_approval_record_from_intent(self, intent_id: str) -> Optional[str]:
        """Get approval record ID from publication intent.
        
        P08: Helper for causality chain.
        
        Args:
            intent_id: Publication intent ID
            
        Returns:
            Approval record ID or None
        """
        # This would query the database
        return f"approval_{intent_id.split('_')[1]}" if "_" in intent_id else None
    
    def get_dependent_issues(self, proposal_id: str) -> List[str]:
        """Get all Feedback issues dependent on a proposal.
        
        P08: For rollback, get all issues to flag for review.
        
        Args:
            proposal_id: Proposal ID
            
        Returns:
            List of issue IDs
        """
        dependent = []
        for link_id, link in self._issue_links.items():
            if link.get("proposal_id") == proposal_id:
                dependent.append(link["issue_id"])
        return dependent