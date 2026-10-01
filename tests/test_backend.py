import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit,parse_qs
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app import assets,catalog,config,db,engine,providers
from app.main import app,JobInput
from app import security

@pytest.fixture
def lab(tmp_path,monkeypatch):
    monkeypatch.setattr(config,"DATA",tmp_path)
    monkeypatch.setattr(config,"DEV",True)
    monkeypatch.setattr(config,"PASSWORD","")
    monkeypatch.setattr(config,"SECRET","test-secret-"*4)
    monkeypatch.setattr(config,"LIVE",False)
    monkeypatch.setattr(config,"PUBLIC_BASE","https://lab.example.com")
    db.init();engine.seed_templates()
    client=TestClient(app)
    client.headers["X-Lab-CSRF"]=client.get('/api/bootstrap').json()['csrf']
    return client

@pytest.fixture
def image(lab):
    b=io.BytesIO();Image.new("RGB",(768,1024),"#d8c4b1").save(b,format="PNG")
    return assets.save_bytes(b.getvalue(),"shirt.png")

def body(a,model="seedream",kind="image",**extra):
    return JobInput(model_id=model,template_id="studio-front" if kind=="image" else "gentle-turn",template_version=1,kind=kind,refs=[{"asset_id":a["id"],"role":"upper" if kind=="image" else "look"}],resolution=catalog.model(model)["resolutions"][0],duration=catalog.model(model)["durations"][0] if catalog.model(model)["durations"] else 3,**extra).model_dump()

def run_until_terminal(jid):
    for _ in range(8):
        db.update_job(jid,next_poll=0)
        engine.tick()
        if db.get_job(jid)["state"] in {"succeeded","failed","uncertain","save_failed"}:break
    return db.get_job(jid)

def test_upload_rejects_fake_image_and_metadata(lab):
    assert lab.post('/api/assets',files={'file':('test.png',b'not a png','image/png')}).status_code==422
    b=io.BytesIO();Image.new("RGB",(600,800)).save(b,format="PNG")
    r=lab.post('/api/assets',files={'file':('image.png',b.getvalue(),'image/png')})
    assert r.status_code==200
    assert "path" not in r.json()
    assert lab.get(r.json()['url']).status_code==200

def test_complete_mock_image_and_video(lab,image):
    b=body(image);j=engine.create_job(b,"test-image-1");row=run_until_terminal(j['id'])
    assert row['state']=='succeeded' and row['actual']==0
    look=db.get_asset(json.loads(row['outputs'])[0])
    blocked=lab.post('/api/jobs',headers={'Idempotency-Key':'test-blocked-video'},json=body(look,'wan-flash','video',image_confirmed=True))
    assert blocked.status_code==422
    review=dict(verdict='pass',clothing=4,identity=4,motion=3,issues=[],notes='',actual_cny=0)
    assert lab.post(f"/api/jobs/{j['id']}/review",json=review).status_code==200
    v=engine.create_job(body(look,'wan-flash','video',image_confirmed=True),'test-video-1')
    result=run_until_terminal(v['id'])
    assert result['state']=='succeeded'
    a=db.get_asset(json.loads(result['outputs'])[0]);assert a['kind']=='video' and a['duration']>=2
    assert lab.get('/api/assets/'+a['id']+'/download').headers['content-type']=='video/mp4'

def test_concurrent_idempotency(lab,image):
    b=body(image)
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids=list(pool.map(lambda _:engine.create_job(b.copy(),'same-operation-key')['id'],range(6)))
    assert len(set(ids))==1
    b['seed']=99
    with pytest.raises(ValueError,match='幂等'):engine.create_job(b,'same-operation-key')

@pytest.mark.parametrize('failure,state',[('generation','failed'),('submit_unknown','uncertain'),('save_once','save_failed')])
def test_failures_never_repost(lab,image,failure,state):
    j=engine.create_job(body(image,mock_failure=failure),'failure-'+failure)
    r=run_until_terminal(j['id']);assert r['state']==state
    tid=r['provider_task_id']
    if state=='save_failed':
        assert lab.post(f"/api/jobs/{j['id']}/resume",json={}).status_code==200
        r=run_until_terminal(j['id']);assert r['state']=='succeeded' and r['provider_task_id']==tid

def test_restart_marks_inflight_uncertain(lab,image):
    j=engine.create_job(body(image),'restart-key')
    db.update_job(j['id'],state='submitting');engine.recover()
    assert db.get_job(j['id'])['state']=='uncertain'
    engine.tick();assert db.get_job(j['id'])['state']=='uncertain'

def test_csrf_auth_and_signed_assets(lab,image,monkeypatch):
    assert lab.post('/api/demo',headers={'X-Lab-CSRF':'invalid'},json={}).status_code==403
    url=security.signed_asset(image['id']);u=urlsplit(url)
    assert lab.get(u.path+'?'+u.query).status_code==200
    assert lab.get(u.path+'?expires=1&sig=invalid').status_code==403
    monkeypatch.setattr(config,'DEV',False)
    assert lab.get('/api/assets').status_code==401
    assert lab.get(u.path+'?'+u.query).status_code==200

def test_login_throttle_persists(lab,monkeypatch):
    monkeypatch.setattr(config,'DEV',False);monkeypatch.setattr(config,'PASSWORD','long-secret-password')
    for _ in range(10):assert lab.post('/api/login',json={'password':'wrong'}).status_code==401
    assert lab.post('/api/login',json={'password':'long-secret-password'}).status_code==429

def test_secret_redaction_and_no_export_links(lab,image,monkeypatch):
    monkeypatch.setenv('ARK_API_KEY','a-test-secret')
    assert security.redact({'Authorization':'Bearer a-test-secret','url':'https://example.com/out?sig=secret','blob':'data:image/png;base64,xxx'})=={'Authorization':'[redacted]','url':'https://example.com/out','blob':'[inline asset omitted]'}
    j=engine.create_job(body(image),'redaction-key');db.update_job(j['id'],result=json.dumps({'urls':['https://example.com?sig=secret']}))
    assert 'sig=secret' not in lab.get('/api/export').text
    assert 'a-test-secret' not in lab.get('/api/bootstrap').text

def test_model_role_and_duration_validation(lab,image):
    b=body(image,'wan-flash','video',image_confirmed=True);b['refs'][0]['role']='upper'
    with pytest.raises(ValueError,match='穿搭图'):engine.validate(b)
    b=body(image,'minimax-h3','video',image_confirmed=True);b['duration']=3
    with pytest.raises(ValueError,match='时长'):engine.validate(b)
    b=body(image,person_mode='self');b['refs'][0]['role']='identity'
    with pytest.raises(ValueError,match='授权'):engine.validate(b)

def test_immutable_template_versions(lab,image):
    j=engine.create_job(body(image),'template-version-key')
    t=engine.templates()[0]
    data={k:v for k,v in t.items() if k not in ('version','workflow','builtin_revision')};data['prompt']='new prompt'
    r=lab.post('/api/templates',json=data);assert r.status_code==200 and r.json()['version']==t['version']+1
    assert json.loads(db.get_job(j['id'])['body'])['template_snapshot']['version']==1

def test_live_requires_enable_consent_key_and_budget(lab,image,monkeypatch):
    b=body(image,'wan-flash','video',image_confirmed=True,mode='live',paid_confirmed=True,max_cost=1)
    with pytest.raises(ValueError,match='开启'):engine.create_job(b,'live-1')
    monkeypatch.setattr(config,'LIVE',True);monkeypatch.setenv('DASHSCOPE_API_KEY','test-key')
    monkeypatch.setattr(config,'DAILY_BUDGET',1)
    j=engine.create_job(b,'live-2')
    assert engine.create_job(b,'live-3')['state']=='queued'
    # Daily count and budget settings no longer block testing; unknown fees stay unknown.
    db.update_job(j['id'],state='failed')
    monkeypatch.setattr(config,'DAILY_CALLS',0)
    assert engine.create_job(b,'live-4')['state']=='queued'

def test_ssrf_rejects_local_result_hosts(monkeypatch):
    monkeypatch.setattr(security.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError,match='内网'):security.public_url('https://example.com/result')
    with pytest.raises(ValueError):security.public_url('http://example.com/result')

@pytest.mark.parametrize('mid',['seedream','qwen-edit','wan-flash','wan-animate','kling-i2v','kling-motion','minimax-h3','vidu-ref','seedance'])
def test_provider_request_contract(lab,image,mid):
    m=catalog.model(mid)
    # Pure builders: no network calls and no billable operations.
    b=body(image,mid,'image' if m['kind']=='image' else 'video',image_confirmed=True)
    b.update(compiled_prompt='Preserve garments',job_id='contract-id')
    if m['kind']=='motion':b['refs'].append({'asset_id':'b'*32,'role':'motion'})
    request=providers.build_request(m,b,preview=True)
    assert request['url'].startswith(config.PROVIDERS[m['provider']]['base'])
    assert 'Authorization' not in request['headers']
    if mid=='wan-flash':assert request['body']['parameters']['audio'] is False
    if mid=='wan-animate':assert 'prompt' not in request['body']['input']
    if mid.startswith('kling'):assert request['body']['settings']['audio']=='off'
    if mid=='minimax-h3':assert request['body']['content'][1]['role']=='first_frame'
    if mid=='seedream':assert 'sequential_image_generation' not in request['body'] # Pro contract has no batch switch
    if mid=='seedance':assert request['body']['generate_audio'] is False

@pytest.mark.parametrize('mid,response,task,url',[
 ('seedream',{'data':[{'url':'https://out.example.com/a.png'}],'usage':{'generated_images':1}},None,'https://out.example.com/a.png'),
 ('qwen-edit',{'output':{'choices':[{'message':{'content':[{'image':'https://out.example.com/a.png'}]}}]}},None,'https://out.example.com/a.png'),
 ('wan-flash',{'output':{'task_id':'wan1','task_status':'SUCCEEDED','video_url':'https://out.example.com/v.mp4'}},'wan1','https://out.example.com/v.mp4'),
 ('wan-animate',{'output':{'task_id':'wan2','task_status':'SUCCEEDED','results':{'video_url':'https://out.example.com/v.mp4'}}},'wan2','https://out.example.com/v.mp4'),
 ('kling-i2v',{'code':0,'data':[{'id':'k1','status':'succeeded','outputs':[{'type':'video','url':'https://out.example.com/v.mp4'}]}]},'k1','https://out.example.com/v.mp4'),
 ('minimax-h3',{'task':{'id':'h3','status':'succeeded','content':{'url':'https://out.example.com/v.mp4'},'usage':{'output_seconds':4}}},'h3','https://out.example.com/v.mp4'),
 ('vidu-ref',{'id':'v1','state':'success','credits':4,'creations':[{'url':'https://out.example.com/v.mp4'}]},'v1','https://out.example.com/v.mp4'),
 ('seedance',{'id':'s1','status':'succeeded','content':{'video_url':'https://out.example.com/v.mp4'}},'s1','https://out.example.com/v.mp4')])
def test_response_normalization(mid,response,task,url):
    r=providers.normalize(catalog.model(mid),response)
    assert r['status']=='succeeded' and r['task_id']==task and r['urls']==[url]

def test_transport_no_automatic_post_retry(lab,image):
    calls=[]
    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout('timeout',request=request)
    client=httpx.Client(transport=httpx.MockTransport(fail))
    b=body(image);b.update(compiled_prompt='test',job_id='test')
    with pytest.raises(providers.AmbiguousSubmission):providers.transport(catalog.model('seedream'),body=b,client=client)
    assert len(calls)==1

def test_cannot_delete_referenced_asset(lab,image):
    engine.create_job(body(image),'referenced-key')
    assert lab.delete('/api/assets/'+image['id']).status_code==422

def test_preview_board_maps_one_image(lab,image):
    p=lab.post('/api/preview',json=body(image,reference_board=True)).json()
    assert p['request']['body']['image']==['asset://reference-board']

def test_csv_formula_escaping(lab,image):
    engine.create_job(body(image,group='=SUM(1,2)'),'csv-formula-key')
    assert "'=SUM(1,2)" in lab.get('/api/export?format=csv').text


def personal_request(image, **settings):
    return JobInput(model_id='tx-kling-image-o1',template_id='personal-image',template_version=1,resolution='2K',ratio='9:16',personal_settings={'face_asset_id':image['id'],'hair_mode':'template','hairstyle':'bob','body_mode':'values','height':172,'weight':65,'consent':True,**settings}).model_dump()


def test_personal_generate_confirm_and_reuse(lab,image):
    b=personal_request(image)
    preview=lab.post('/api/preview',json=b)
    assert preview.status_code==200,preview.text
    assert '172厘米' in preview.json()['prompt'] and '短波波头' in preview.json()['prompt']
    assert '84%' in preview.json()['prompt'] and '素色长裤' in preview.json()['prompt']
    j=engine.create_job(b,'personal-first-job')
    row=run_until_terminal(j['id']);assert row['state']=='succeeded'
    aid=json.loads(row['outputs'])[0]
    frozen=json.loads(row['body'])['personal_settings']
    save={'settings':frozen,'job_id':j['id'],'asset_id':aid,'confirmed':False}
    assert lab.post('/api/personal-profiles',json=save).status_code==422
    save['confirmed']=True
    p=lab.post('/api/personal-profiles',json=save);assert p.status_code==200,p.text
    pid=p.json()['id'];assert lab.post('/api/personal-profiles',json=save).json()['id']==pid
    assert len(lab.get('/api/personal-profiles').json()['profiles'])==1
    reuse=body(image,model='tx-kling-image-o1',identity_consent=True,person_mode='self',personal_profile_id=pid)
    reuse['refs'].insert(0,{'asset_id':aid,'role':'body'})
    checked=engine.validate(reuse)
    assert checked['personal_profile_snapshot']['asset_id']==aid
    assert '基础T恤和长裤必须替换' in checked['compiled_prompt']
    assert lab.delete('/api/assets/'+aid).status_code==422
    assert lab.delete('/api/personal-profiles/'+pid).status_code==200
    assert checked['personal_profile_snapshot']['asset_id']==aid
    assert lab.get('/api/personal-profiles').json()['profiles']==[]


@pytest.mark.parametrize('changes',[{'consent':False},{'face_asset_id':None},{'body_mode':'photo'},{'hairstyle':'unknown'},{'height':230},{'weight':20},{'hair_mode':'template','hairstyle':'custom','hair_details':''}])
def test_personal_invalid_settings_do_not_submit(lab,image,changes):
    b=personal_request(image)
    b['personal_settings'].update(changes)
    r=lab.post('/api/jobs',headers={'Idempotency-Key':'invalid-personal-request'},json=b)
    assert r.status_code==422
    assert lab.get('/api/jobs').json()==[]


def test_personal_input_switches_and_model_capacity(lab,image):
    second=assets.save_bytes((config.DATA/'assets'/image['path']).read_bytes(),'body.png')
    b=personal_request(image,body_asset_id=second['id'],body_mode='photo',hair_mode='photo')
    checked=engine.validate(b)
    assert len(checked['refs'])==2
    assert [r['role'] for r in checked['refs']]==['identity','body']
    b['model_id']='tx-kling-image-v3'
    assert lab.post('/api/preview',json=b).status_code==422
    b['model_id']='tx-kling-image-o1';b['personal_settings'].update(face_mode='description',appearance='成年女性，自然五官',hair_mode='template',body_mode='values')
    assert engine.validate(b)['refs']==[]
    b['personal_settings'].update(face_mode='photo',face_asset_id=None,body_mode='photo')
    assert len(engine.validate(b)['refs'])==1


def test_mock_personal_cannot_enter_paid_outfit(lab,image):
    j=engine.create_job(personal_request(image),'personal-mock-live-test');row=run_until_terminal(j['id'])
    aid=json.loads(row['outputs'])[0];p=lab.post('/api/personal-profiles',json={'settings':json.loads(row['body'])['personal_settings'],'job_id':j['id'],'asset_id':aid,'confirmed':True}).json()
    b=body(image,model='tx-kling-image-o1',mode='live',identity_consent=True,paid_confirmed=True,personal_profile_id=p['id']);b['refs'].insert(0,{'asset_id':aid,'role':'body'})
    r=lab.post('/api/preview',json=b)
    assert r.status_code==422 and '模拟形象' in r.json()['detail']


def test_personal_fullbody_prompt_reaches_provider(lab,image):
    b=personal_request(image)
    b['model_id']='tx-kling-image-v3'
    checked=engine.validate(b)
    request=providers.build_request(checked['model_snapshot'],checked,True)
    assert request['body']['prompt']==checked['compiled_prompt']
    assert '完整成人的全身' in request['body']['prompt']
    assert '不是抠出头像' in request['body']['prompt']
    assert '82%–86%' in request['body']['prompt']
    assert request['body']['image']=='asset://'+image['id']
    assert request['body']['n']==1
    assert checked['personal_settings']['body_mode']=='values'
    assert checked['asset_snapshot'][0]['role']=='identity'
    assert engine.template('personal-image',1)['negative_prompt']!=engine.template('personal-image',2)['negative_prompt']
