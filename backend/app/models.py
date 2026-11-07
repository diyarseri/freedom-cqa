"""Wire input validation. Unknown fields are errors, including provider output."""
import math
import re
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(min_length=1)]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
PositiveInt = Annotated[StrictInt, Field(ge=1)]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='after')
    def nonblank(self):
        for value in self.__dict__.values():
            if isinstance(value, str) and not value.strip():
                raise ValueError('Text fields must not be blank')
        return self


class SourceMessage(Model):
    timestamp: Text
    speaker: Literal['client', 'operator', 'bot', 'system']
    text: Text


class SourceRecord(Model):
    conversation_id: Text
    channel: Literal['agent chat', 'voice call']
    language: Literal['RU', 'KZ', 'EN']
    transcript: Annotated[list[SourceMessage], Field(min_length=1)]
    audio_url: str | None

    @model_validator(mode='after')
    def check_source(self):
        if self.channel == 'agent chat' and self.audio_url is not None:
            raise ValueError('Chat audio_url must be null')
        if self.audio_url is not None:
            u = urlsplit(self.audio_url)
            if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password:
                raise ValueError('audio_url must be an absolute HTTP(S) URL without credentials')
        for m in self.transcript:
            if self.channel == 'agent chat':
                if not re.fullmatch(r'\d{2,}:[0-5]\d', m.timestamp):
                    raise ValueError('Chat timestamp must be MM:SS')
            else:
                if not re.match(r'^\d{4}-\d\d-\d\dT', m.timestamp):
                    raise ValueError('Call timestamp must be ISO8601 with timezone')
                try:
                    parsed = datetime.fromisoformat(m.timestamp.replace('Z', '+00:00'))
                except ValueError:
                    raise ValueError('Invalid call timestamp') from None
                if parsed.utcoffset() is None:
                    raise ValueError('Call timestamp needs timezone')
        return self


class ImportRequest(Model):
    group_id: Text


class InspectedRange(Model):
    start_message_id: Text
    end_message_id: Text


class Evidence(Model):
    message_ids: list[Text]
    inspected_ranges: list[InspectedRange]


class Section(Model):
    section_id: Text
    title: Text


class ScaleAnchor(Model):
    value: Number
    wording: Text


class Criterion(Model):
    criterion_id: Text
    section_id: str | None
    title: Text
    wording: Text
    weight: Annotated[Number, Field(ge=0)]
    answer_type: Literal['boolean', 'numeric']
    allowed_numeric_values: list[Number]
    maximum: Number | None
    na_allowed: StrictBool
    na_condition: str | None
    effect: Literal['score', 'gross_error']
    scale: list[ScaleAnchor]

    @model_validator(mode='after')
    def criterion_config(self):
        if self.na_allowed != bool(self.na_condition and self.na_condition.strip()):
            raise ValueError('N/A requires a nonblank condition iff allowed')
        if not self.na_allowed and self.na_condition is not None:
            raise ValueError('Disallowed N/A condition must be null')
        if self.answer_type == 'boolean':
            if self.maximum is not None or self.allowed_numeric_values or self.scale:
                raise ValueError('Boolean criteria have no numeric scale')
        else:
            values = self.allowed_numeric_values
            if (self.maximum is None or self.maximum <= 0 or not values
                or len(values) != len(set(values)) or 0 not in values
                or self.maximum not in values or any(v < 0 or v > self.maximum for v in values)):
                raise ValueError('Invalid numeric scale or maximum')
            anchors = [a.value for a in self.scale]
            if len(anchors) != len(values) or set(anchors) != set(values):
                raise ValueError('Exactly one anchor required per allowed numeric value')
        if self.effect == 'gross_error' and (self.answer_type != 'boolean' or self.weight != 0 or self.na_allowed):
            raise ValueError('Gross-error criterion must be boolean, weight 0, N/A disabled')
        return self


class ChecklistInput(Model):
    name: Text
    sections: list[Section]
    criteria: Annotated[list[Criterion], Field(min_length=1)]

    @model_validator(mode='after')
    def references(self):
        sections = [s.section_id for s in self.sections]
        ids = [c.criterion_id for c in self.criteria]
        if len(sections) != len(set(sections)) or len(ids) != len(set(ids)):
            raise ValueError('Duplicate section or criterion ID')
        if any(c.section_id is not None and c.section_id not in sections for c in self.criteria):
            raise ValueError('Unknown section ID')
        if not math.isfinite(sum(c.weight for c in self.criteria if c.effect == 'score')):
            raise ValueError('Aggregate scoring weight must be finite')
        if sum(c.effect == 'gross_error' for c in self.criteria) > 1:
            raise ValueError('At most one gross-error criterion')
        return self


class ChecklistUpdate(Model):
    expected_version: PositiveInt
    configuration: ChecklistInput


class Judgment(Model):
    criterion_id: Text
    answer: Literal['yes', 'no', 'numeric', 'na']
    numeric_value: Number | None
    rationale: Text
    evidence: Evidence

    @model_validator(mode='after')
    def numeric_shape(self):
        if (self.answer == 'numeric') != (self.numeric_value is not None):
            raise ValueError('numeric_value required only for numeric answer')
        return self


class ProviderJudgments(Model):
    judgments: list[Judgment]


class EvaluationRequest(Model):
    conversation_id: Text
    checklist_id: Text
    checklist_version: PositiveInt


class AppealRequest(Model):
    expected_revision: PositiveInt
    criterion_id: Text
    comment: Text
    evidence: Evidence = Field(default_factory=lambda: Evidence(message_ids=[], inspected_ranges=[]))


class DecisionRequest(Model):
    expected_revision: PositiveInt
    action: Literal['confirm', 'change']
    reason: Text
    replacement: Judgment | None

    @model_validator(mode='after')
    def replacement_shape(self):
        if (self.action == 'change') != (self.replacement is not None):
            raise ValueError('Change requires replacement; confirm requires null')
        return self
