"""Validated judgments in; deterministic Decimal arithmetic out. No model calls."""
from decimal import Decimal, ROUND_HALF_UP, localcontext

from pydantic import ValidationError

from .models import Judgment


class InvalidJudgment(ValueError):
    pass


def validate_evidence(evidence, conversation, required=False):
    ordinals = {m['message_id']: m['ordinal'] for m in conversation['messages']}
    if required and not evidence.message_ids and not evidence.inspected_ranges:
        raise InvalidJudgment('Evidence must contain a message or inspected range')
    if any(id not in ordinals for id in evidence.message_ids):
        raise InvalidJudgment('Unknown evidence message ID')
    for r in evidence.inspected_ranges:
        if r.start_message_id not in ordinals or r.end_message_id not in ordinals:
            raise InvalidJudgment('Unknown inspected-range message ID')
        if ordinals[r.start_message_id] > ordinals[r.end_message_id]:
            raise InvalidJudgment('Inspected range is reversed')


def validate_judgment(j, criterion, conversation):
    if j.criterion_id != criterion['criterion_id']:
        raise InvalidJudgment('Criterion ID does not match')
    if j.answer == 'na':
        if not criterion['na_allowed']:
            raise InvalidJudgment('N/A is not allowed for this criterion')
    elif criterion['answer_type'] == 'boolean':
        if j.answer not in ('yes', 'no'):
            raise InvalidJudgment('Boolean criterion requires yes/no')
    elif j.answer != 'numeric' or j.numeric_value not in criterion['allowed_numeric_values']:
        raise InvalidJudgment('Numeric criterion requires an allowed discrete value')
    validate_evidence(j.evidence, conversation, required=True)


def validate_judgments(judgments, checklist, conversation):
    try:
        parsed = [Judgment.model_validate(j) if isinstance(j, dict) else j for j in judgments]
    except ValidationError:
        raise InvalidJudgment('Malformed judgment structure') from None
    ids = [j.criterion_id for j in parsed]
    expected = [c['criterion_id'] for c in checklist['criteria']]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise InvalidJudgment('Judgments must cover every saved criterion exactly once')
    by_id = {j.criterion_id: j for j in parsed}
    ordered = [by_id[cid] for cid in expected]
    for j, c in zip(ordered, checklist['criteria']):
        validate_judgment(j, c, conversation)
    return ordered


def calculate(checklist, judgments, conversation):
    js = validate_judgments(judgments, checklist, conversation)
    with localcontext() as ctx:
        ctx.prec = 50
        return _calculate(checklist, js)


def _calculate(checklist, js):
    D = lambda value: Decimal(str(value))
    applicable = [c['effect'] == 'score' and j.answer != 'na' for c, j in zip(checklist['criteria'], js)]
    denominator = sum((D(c['weight']) for c, a in zip(checklist['criteria'], applicable) if a), Decimal(0))
    scores, raw_sum = [], Decimal(0)
    # Keep Decimal values through section and total aggregation; serialize only at the boundary.
    decimal_scores = []
    gross = None
    for c, j, a in zip(checklist['criteria'], js, applicable):
        if c['effect'] == 'gross_error':
            gross = j.answer == 'yes'
        raw = effective = points = None
        if a:
            normalized = D(j.numeric_value)/D(c['maximum']) if j.answer == 'numeric' else D(int(j.answer == 'yes'))
            raw = D(c['weight'])*normalized
            raw_sum += raw
            if denominator:
                effective = D(c['weight'])*100/denominator
                points = raw*100/denominator
        decimal_scores.append((c, points, effective))
        scores.append(dict(criterion_id=c['criterion_id'], weight=c['weight'],
                           raw_points=float(raw) if raw is not None else None,
                           effective_weight=float(effective) if effective is not None else None,
                           points=float(points) if points is not None else None))
    sections = []
    for section in checklist['sections']:
        items = [(p, w) for c, p, w in decimal_scores if c['section_id'] == section['section_id'] and p is not None]
        sections.append(dict(section_id=section['section_id'],
                             points=float(sum(p for p, _ in items)) if items else None,
                             maximum=float(sum(w for _, w in items)) if items else None))
    total = float((raw_sum*100/denominator).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if denominator else None
    return dict(judgments=[j.model_dump() for j in js], scores=scores, sections=sections,
                applicable_weight=float(denominator), total=total,
                total_unavailable_reason=None if denominator else 'no_applicable_weight', gross_error=gross)
