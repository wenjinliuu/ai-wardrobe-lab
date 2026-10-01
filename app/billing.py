"""Receipt reconciliation. Billable units are not text tokens or estimated pixels."""
from decimal import Decimal, ROUND_HALF_UP
from . import config, pricing

def rounded(value):
    return float(Decimal(str(value)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))

def context(body):
    model = body['model_snapshot']
    spec = model.get('billing', {})
    # Older experiments retain their own model price snapshot. Known TokenHub
    # tariff applies only to the enumerated current profiles, not every provider.
    if not spec and model['provider'] == 'tokenhub':
        # Do not retrofit today's tariff onto an old experiment as if it were
        # captured at submission. A historical receipt needs its own rate.
        spec = {'verification': 'historical_missing'}
    if not spec and model['pricing']['type'] == 'token':
        video = any(x['kind'] == 'video' for x in body['asset_snapshot'])
        rates = model['pricing'].get('video_rates_million' if video else 'rates_million', {})
        spec = {'unit': 'tokens', 'rate': rates.get(body['resolution']), 'rate_basis': 1000000,
                'verification': 'previous_profile'}
    quote = pricing.estimate(body)
    rate = spec.get('rate')
    reference_units = None
    if rate and quote['reference_cny'] is not None:
        reference_units = rounded(Decimal(str(quote['reference_cny'])) * Decimal(str(spec['rate_basis'])) / Decimal(str(rate)))
    return dict(unit=spec.get('unit'), rate=rate, rate_basis=spec.get('rate_basis'),
                verification=spec.get('verification', 'official' if rate else 'not_token_billed'),
                date=spec.get('checked_at', model.get('price_date')),
                source=spec.get('source', model.get('price_source')),
                reference_cny=quote['reference_cny'], reference_units=reference_units,
                breakdown=quote['breakdown'], pricing_type=model['pricing']['type'],
                note='金额反推的是按所用单价折算的计费量，不是供应商实测Token。免费额度、折扣和混合单价可能无法反推；可同时填写金额与用量核对差额。')

def reconcile(body, receipt):
    ctx = body.get('billing_snapshot') or context(body)
    mode = receipt.get('billing_mode', 'amount')
    amount = receipt.get('actual_cny')
    units = receipt.get('billed_units')
    unit = receipt.get('billing_unit') or ctx['unit']
    override = receipt.get('rate_override')
    rate = override if override is not None else ctx['rate'] if unit == ctx['unit'] else None
    basis = 1000000 if unit == 'tokens' else 1 if unit == 'credits' else None
    if override is not None and not receipt.get('rate_note', '').strip():
        raise ValueError('自定义单价请注明账户折扣或账单依据')
    if mode in ('units', 'both'):
        if units is None: raise ValueError('请填写供应商账单的实际计费用量')
        if not rate or not basis: raise ValueError('该渠道没有可核对的Token/积分单价，请填写实际单价及依据，或改用金额核对')
    if mode == 'both' and amount is None: raise ValueError('同时核对需要填写账单金额')
    if mode == 'amount' and units is not None: raise ValueError('金额模式不能把反推用量作为实际用量提交')
    calculated = rounded(Decimal(str(units)) * Decimal(str(rate)) / basis) if units is not None and rate and basis else None
    actual = calculated if mode == 'units' else amount
    if actual is not None and actual > 10000:
        raise ValueError('本测试台单条核对金额上限为10000元，请检查用量和单价单位')
    if body['mode'] == 'mock':
        if actual not in (None, 0) or units not in (None, 0): raise ValueError('模拟任务没有真实模型费用或计费用量')
        actual = 0
    inferred = rounded(Decimal(str(actual)) * basis / Decimal(str(rate))) if mode == 'amount' and actual is not None and actual > 0 and rate and basis else None
    return dict(actual_cny=actual, actual_units=units if mode in ('units', 'both') else None,
                inferred_units=inferred, unit=unit, rate=rate, rate_basis=basis,
                calculated_cny=calculated,
                difference_cny=rounded(Decimal(str(amount)) - Decimal(str(calculated))) if mode == 'both' else None,
                cost_source='mock' if body['mode'] == 'mock' else 'units_calculated' if mode == 'units' else 'receipt' if actual is not None else 'pending',
                price_snapshot=ctx, rate_note=receipt.get('rate_note', ''), reference=receipt.get('bill_reference', ''))
