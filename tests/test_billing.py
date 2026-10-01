"""Receipt math and experiment lineage; no paid or external calls."""
import json
from copy import deepcopy
import pytest
from app import billing, catalog, db, engine, pricing
from test_backend import lab, image, body, run_until_terminal


def sample(mid='tx-minimax-video-h3-max', **extra):
    m=deepcopy(catalog.model(mid))
    return dict(model_snapshot=m,asset_snapshot=[],resolution=m['resolutions'][0],duration=6,mode='live',video_mode=m['default_mode'],audio_mode='off',reference_board=False,ratio='9:16',**extra)


def test_token_bidirectional_math_and_receipt_difference():
    b=sample();ctx=billing.context(b)
    assert ctx['unit']=='tokens' and ctx['rate']==10 and ctx['rate_basis']==1000000
    assert ctx['reference_cny']==1.98 and ctx['reference_units']==198000
    r=billing.reconcile(b,dict(billing_mode='units',billed_units=198000))
    assert r['actual_cny']==1.98 and r['actual_units']==198000 and r['inferred_units'] is None
    assert r['cost_source']=='units_calculated'
    r=billing.reconcile(b,dict(actual_cny=1.98))
    assert r['inferred_units']==198000 and r['actual_units'] is None
    r=billing.reconcile(b,dict(billing_mode='both',actual_cny=1.5,billed_units=198000))
    assert r['difference_cny']==-.48 and r['actual_cny']==1.5


def test_unit_price_override_is_explicit_and_frozen():
    b=sample();b['billing_snapshot']=billing.context(b)
    b['model_snapshot']['billing']['rate']=999
    assert billing.reconcile(b,dict(billing_mode='units',billed_units=100000))['actual_cny']==1
    with pytest.raises(ValueError,match='依据'):
        billing.reconcile(b,dict(billing_mode='units',billed_units=100000,rate_override=7))
    r=billing.reconcile(b,dict(billing_mode='units',billed_units=100000,rate_override=7,rate_note='账户折扣'))
    assert r['actual_cny']==.7 and r['rate_note']=='账户折扣'
    assert r['price_snapshot']['rate']==10


def test_non_token_model_and_historical_tariff_not_invented():
    b=sample('native-MiniMax-H3-Max')
    assert billing.context(b)['unit'] is None
    assert billing.reconcile(b,dict(actual_cny=1.98))['inferred_units'] is None
    with pytest.raises(ValueError,match='单价'):
        billing.reconcile(b,dict(billing_mode='units',billed_units=198000,billing_unit='tokens'))
    old=sample();old['model_snapshot'].pop('billing')
    assert billing.context(old)['verification']=='historical_missing'
    assert billing.context(old)['rate'] is None
    assert billing.reconcile(old,dict(actual_cny=1.98))['inferred_units'] is None


def test_credit_units_and_zero_receipt():
    mid=next(m['id'] for m in catalog.MODELS if m.get('billing',{}).get('unit')=='credits')
    r=billing.reconcile(sample(mid),dict(billing_mode='units',billing_unit='credits',billed_units=5))
    assert r['actual_cny']==5 and r['rate_basis']==1
    assert billing.reconcile(sample(),dict(actual_cny=0))['inferred_units'] is None


def test_mock_nonzero_and_oversized_receipt_rejected():
    b=sample();b['mode']='mock'
    with pytest.raises(ValueError,match='模拟'):
        billing.reconcile(b,dict(actual_cny=1))
    assert billing.reconcile(b,dict())['actual_cny']==0
    with pytest.raises(ValueError,match='10000'):
        billing.reconcile(sample(),dict(billing_mode='units',billed_units=2000000000))


def test_reference_video_tariff_not_applied_to_images():
    b=sample('tx-vidu-video-q3-turbo');b['video_mode']='reference';b['resolution']='720p'
    b['asset_snapshot']=[{'kind':'image'}]
    image_price=pricing.estimate(b)['reference_cny']
    b['asset_snapshot']=[{'kind':'video','duration':3}]
    video_price=pricing.estimate(b)['reference_cny']
    assert image_price!=video_price


def test_assets_link_job_billing_and_observed_specs(lab,image):
    j=engine.create_job(body(image),'lineage-evaluation');row=run_until_terminal(j['id'])
    output=json.loads(row['outputs'])[0]
    receipt=dict(verdict='pass',clothing=4,identity=4,background=5,framing=4,detail=3,issues=['非白背景'],notes='模拟流程',actual_cny=0)
    assert lab.post('/api/jobs/'+j['id']+'/review',json=receipt).status_code==200
    materials={a['id']:a for a in lab.get('/api/assets').json()}
    assert materials[image['id']]['provenance']=={'type':'upload','upload_origin':'unknown'}
    a=materials[output];p=a['provenance']
    assert p['type']=='mock_generated' and p['job_id']==j['id']
    assert p['model']==catalog.model('seedream')['model']
    assert p['billing']['cost_source']=='mock' and p['actual_cny']==0
    assert a['width']>0 and a['height']>0 and a['size']>0
    assert 'path' not in a
    preview=lab.post('/api/jobs/'+j['id']+'/billing-preview',json={'actual_cny':1})
    assert preview.status_code==422
    csv=lab.get('/api/export?format=csv').text
    assert '选定清晰度' in csv and '账单差额CNY' in csv and '输出文件规格' in csv


def test_real_receipt_api_updates_provenance_without_paid_call(lab,image):
    j=engine.create_job(body(image),'real-receipt-local');run_until_terminal(j['id'])
    # Simulate stored live data only, never submit or poll a provider.
    stored=json.loads(db.get_job(j['id'])['body']);stored['mode']='live'
    stored['billing_snapshot']=billing.context(sample())
    with db.connection() as c:
        c.execute('UPDATE jobs SET body=?,result=? WHERE id=?',(json.dumps(stored),json.dumps({'usage':{'total_tokens':198000,'secret':'must-not-export'}}),j['id']))
    url='/api/jobs/'+j['id']
    record=dict(verdict='pass',clothing=4,identity=4,billing_mode='units',billing_unit='tokens',billed_units=198000)
    assert lab.post(url+'/billing-preview',json={'billing_mode':'units','billing_unit':'tokens','billed_units':198000}).json()['actual_cny']==1.98
    assert lab.post(url+'/review',json=record).status_code==200
    detail=lab.get(url).json();assert detail['actual']==1.98
    p=next(a for a in lab.get('/api/assets').json() if a['source']==j['id'])['provenance']
    assert p['type']=='generated' and p['billing']['actual_units']==198000
    assert p['reported_usage']=={'total_tokens':198000}
    assert 'must-not-export' not in lab.get('/api/export').text
    assert lab.post(url+'/billing-preview',json={'billed_units':-1}).status_code==422


def test_builtin_white_revision_keeps_custom_history(lab,image):
    latest=engine.templates()
    assert all('纯白' in t['prompt'] for t in latest)
    full=next(t for t in latest if t['id']=='full-turn-360')
    assert '360' in full['prompt'] and '固定' in full['prompt']
    old=engine.template('studio-front',1)
    white=engine.template('studio-front',2)
    assert old['prompt']!=white['prompt']
    engine.seed_templates();assert engine.template('studio-front',2)==white
    with db.connection() as c:
        c.execute("DELETE FROM templates WHERE id='studio-front' AND version=2")
        custom=dict(old,version=2,prompt='用户旧模板')
        c.execute('INSERT INTO templates VALUES(?,?,?,?)',('studio-front',2,json.dumps(custom),db.now()))
    engine.seed_templates()
    assert engine.template('studio-front',2)['prompt']=='用户旧模板'
    assert '纯白' in engine.template('studio-front',3)['prompt']
    engine.seed_templates();assert next(t for t in engine.templates() if t['id']=='studio-front')['version']==3


def test_upload_origin_self_and_user_are_separate(lab,image):
    from app import config
    content=(config.DATA/'assets'/image['path']).read_bytes()
    for origin in ('self','user'):
        r=lab.post('/api/assets',data={'origin':origin},files={'file':('origin.png',content,'image/png')})
        assert r.status_code==200
        assert r.json()['provenance']=={'type':'upload','upload_origin':origin}
    assert lab.post('/api/assets',data={'origin':'invented'},files={'file':('origin.png',content,'image/png')}).status_code==422
