"""Data model: everything ContractIQ extracts, as validated Pydantic objects.

Every extracted item carries its *evidence* (a verbatim quote) and the *page* it
came from, so a human can verify any row in seconds. `grounded` records whether
that quote was actually found in the source document (a guard against an LLM
inventing text).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Obligation = Literal["shall", "must", "will", "should", "required"]
Party = Literal["contractor", "offeror", "government", "unspecified"]
Category = Literal[
    "technical", "management", "cost_price", "past_performance", "security",
    "deliverable", "schedule", "legal_clause", "proposal_instruction", "other",
]


class _Item(BaseModel):
    """Fields shared by every extracted item."""
    model_config = ConfigDict(extra="ignore")

    page: int | None = Field(default=None, description="1-based page where the evidence appears")
    evidence: str = Field(default="", description="Verbatim text from the document supporting this item")
    grounded: bool = Field(default=True, description="False if the evidence could not be found in the document")


class Requirement(_Item):
    id: str = ""
    text: str = Field(min_length=8, description="The requirement, as written in the document")
    obligation: Obligation = "shall"
    party: Party = "unspecified"
    mandatory: bool = True
    category: Category = "other"
    section: str = Field(default="", description="Paragraph or section reference, e.g. C.3.2")
    source: Literal["rules", "llm"] = "rules"


class KeyDate(_Item):
    label: str = Field(description="What the date is, e.g. 'Proposals due'")
    date: str = Field(default="", description="ISO date YYYY-MM-DD, or empty if it could not be parsed")
    time: str = Field(default="", description="Time and zone as written, e.g. '2:00 PM CT'")
    raw: str = Field(default="", description="The date exactly as written")


class MoneyItem(_Item):
    label: str = Field(description="e.g. 'ceiling', 'minimum guarantee', 'not-to-exceed'")
    amount: float
    raw: str = ""


class Clin(_Item):
    number: str
    description: str = ""
    type: str = Field(default="", description="Pricing type such as FFP or T&M")


class Deliverable(_Item):
    id: str = Field(description="CDRL identifier such as A001")
    title: str = ""
    frequency: str = ""
    due: str = ""


class EvaluationFactor(_Item):
    name: str
    importance: str = Field(default="", description="Relative importance as stated, e.g. 'significantly more important than Factor 2'")
    subfactors: list[str] = Field(default_factory=list)


class ContractTerms(BaseModel):
    model_config = ConfigDict(extra="ignore")

    solicitation_number: str = ""
    title: str = ""
    agency: str = ""
    contract_type: str = ""
    naics: str = ""
    set_aside: str = ""
    period_of_performance: str = ""
    place_of_performance: str = ""
    amounts: list[MoneyItem] = Field(default_factory=list)


class Metadata(BaseModel):
    source_file: str = ""
    page_count: int = 0
    mode: Literal["rules", "llm"] = "rules"
    model: str = ""
    contractiq_version: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


class Extraction(BaseModel):
    """The full result for one document."""
    metadata: Metadata = Field(default_factory=Metadata)
    terms: ContractTerms = Field(default_factory=ContractTerms)
    key_dates: list[KeyDate] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    evaluation_factors: list[EvaluationFactor] = Field(default_factory=list)
    deliverables: list[Deliverable] = Field(default_factory=list)
    clins: list[Clin] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def stats(self) -> dict[str, int]:
        r = self.requirements
        return {
            "requirements": len(r),
            "mandatory": sum(x.mandatory for x in r),
            "key_dates": len(self.key_dates),
            "evaluation_factors": len(self.evaluation_factors),
            "deliverables": len(self.deliverables),
            "clins": len(self.clins),
            "ungrounded": sum(not x.grounded for x in self.evidence_items()),
        }

    def evidence_items(self) -> list[_Item]:
        return [*self.requirements, *self.key_dates, *self.terms.amounts, *self.clins,
                *self.deliverables, *self.evaluation_factors]


# ---------------------------------------------------------------------------
# What the LLM is asked to return for one chunk of the document.
# Kept separate from the models above so the tool schema stays small and the
# model is never asked to invent ids or bookkeeping fields.
# ---------------------------------------------------------------------------
class RequirementIn(BaseModel):
    text: str = Field(min_length=8, description="The requirement, as written")
    evidence: str = Field(min_length=8, description="Verbatim quote from the document (copy exactly, do not paraphrase)")
    page: int = Field(description="Page number from the nearest [[PAGE n]] marker above the quote")
    obligation: Obligation = Field(description="The modal word used: shall, must, will, should, or required")
    party: Party = Field(description="Who must act. 'government' for Government obligations")
    category: Category
    section: str = Field(default="", description="Paragraph reference such as C.3.2, if shown")


class KeyDateIn(BaseModel):
    label: str
    date: str = Field(default="", description="ISO format YYYY-MM-DD if a full date is given, else empty")
    time: str = ""
    raw: str = Field(default="", description="Date as written")
    evidence: str = Field(min_length=4)
    page: int


class MoneyItemIn(BaseModel):
    label: str
    amount: float
    raw: str = ""
    evidence: str = Field(min_length=4)
    page: int


class ClinIn(BaseModel):
    number: str
    description: str = ""
    type: str = ""
    evidence: str = Field(min_length=4)
    page: int


class DeliverableIn(BaseModel):
    id: str
    title: str = ""
    frequency: str = ""
    due: str = ""
    evidence: str = Field(min_length=4)
    page: int


class EvaluationFactorIn(BaseModel):
    name: str
    importance: str = ""
    subfactors: list[str] = Field(default_factory=list)
    evidence: str = Field(min_length=4)
    page: int


class TermsIn(BaseModel):
    solicitation_number: str = ""
    title: str = ""
    agency: str = ""
    contract_type: str = ""
    naics: str = ""
    set_aside: str = ""
    period_of_performance: str = ""
    place_of_performance: str = ""


class ChunkResult(BaseModel):
    """The single tool input the LLM fills in for one chunk of the document."""
    terms: TermsIn = Field(default_factory=TermsIn)
    requirements: list[RequirementIn] = Field(default_factory=list)
    key_dates: list[KeyDateIn] = Field(default_factory=list)
    amounts: list[MoneyItemIn] = Field(default_factory=list)
    clins: list[ClinIn] = Field(default_factory=list)
    deliverables: list[DeliverableIn] = Field(default_factory=list)
    evaluation_factors: list[EvaluationFactorIn] = Field(default_factory=list)
