# backend/app/domain/enums.py
from enum import StrEnum


class ProvenanceClass(StrEnum):
    """
    PRD Section 5.1: Every item in the case engine carries exactly one provenance class.
    Tracks *how* a piece of information entered the world.
    """
    PHYSICAL = "PHYSICAL"              # Physical trace (e.g., broken watch, fingerprints)
    RECORD = "RECORD"                  # Digital/paper log (e.g., study door badge swipe at 21:52)
    WITNESS = "WITNESS"                # Third-party observation (e.g., neighbour saw suspect)
    SELF_REPORT = "SELF_REPORT"        # Suspect's own statement during interrogation
    MODEL_INFERRED = "MODEL_INFERRED"  # Output from the ML ranker or consistency engine


class VerificationStatus(StrEnum):
    """
    PRD Section 5.1: Tracks epistemological certainty of a Fact or Claim.
    Claims start as UNVERIFIED and can never be auto-promoted to ESTABLISHED by a model.
    """
    ESTABLISHED = "ESTABLISHED"  # Grounded baseline evidence (e.g., verified crime scene logs)
    VERIFIED = "VERIFIED"        # Corroborated by independent reliable facts
    UNVERIFIED = "UNVERIFIED"    # Default state for all player and suspect claims (MD-04)
    DISPUTED = "DISPUTED"        # Conflicts with another claim or low-reliability witness
    REFUTED = "REFUTED"          # Directly contradicted by an ESTABLISHED fact


class EvidenceCategory(StrEnum):
    """
    PRD Section 5.3: Used to compute `evidence_coverage` (fraction of categories discovered)
    and map specific facts to feature derivations (`access_evidence`, `motive_evidence`).
    """
    TIMELINE = "TIMELINE"        # Whereabouts and movement records
    ACCESS = "ACCESS"            # Keycards, keys, weapon possession, restricted entry
    MOTIVE = "MOTIVE"            # Financial debt, inheritance, blackmail, arguments
    FORENSIC = "FORENSIC"        # Physical scene traces
    RELATIONSHIP = "RELATIONSHIP"# Evidence revealing an edge between two characters (CH-06)


class ContradictionType(StrEnum):
    """
    PRD Section 6.4.B: Recorded by the consistency engine when flagging conflicts.
    """
    CLAIM_FACT = "CLAIM_FACT"    # Suspect's claim is refuted by an established fact
    CLAIM_CLAIM = "CLAIM_CLAIM"  # Suspect contradicted their own earlier statement


class InteractionType(StrEnum):
    """
    PRD Section 7A.3: Closed set of social simulation interactions.
    v0.1 implements the first three; v0.2 adds the remaining three.
    """
    ARGUE = "ARGUE"              # v0.1: Lowers affinity, creates witness fact / motive
    CONFIDE = "CONFIDE"          # v0.1: Shares secret, raises trust, creates T2 asymmetry
    COVER_FOR = "COVER_FOR"      # v0.1: High loyalty/obligation -> false/partial alibi claim
    GOSSIP = "GOSSIP"            # v0.2: Spreads secret to 3rd party with lower reliability
    BLACKMAIL = "BLACKMAIL"      # v0.2: High greed + secret -> creates motive & financial record
    AVOID = "AVOID"              # v0.2: Low affinity -> suppresses co-location


class DialogueAct(StrEnum):
    """
    PRD Section 7.2: Chosen deterministically by the Mode 2 interrogation state machine.
    The LLM only verbalises the chosen act; it never chooses the act itself.
    """
    ANSWER = "ANSWER"
    DEFLECT = "DEFLECT"
    DENY = "DENY"
    LIE_PER_COVER_STORY = "LIE_PER_COVER_STORY"
    PARTIAL_ADMISSION = "PARTIAL_ADMISSION"
    CONFESS = "CONFESS"
    UNKNOWN = "UNKNOWN"