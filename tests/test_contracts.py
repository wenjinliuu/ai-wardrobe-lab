"""Nonbillable, model/mode-specific validation and wire-format regression tests."""
import io,json,uuid,wave
import httpx,pytest
from PIL import Image
from app import assets,catalog,config,db,engine,providers
from app.main import JobInput
from tests.test_backend import lab,image,body

CASES=[(m['id'],mode) for m in catalog.MODELS for mode in m['modes']]

def mode_body(m,mode,image):
    spec=m['modes'][mode];refs=[]
    for u,count in spec.get('required',{}).items():
        for _ in range(count):refs.append(ref_for(u,image))
    if spec.get('require_any'):
        u=next(u for u,n in spec['limits'].items() if n and u!='element');refs.append(ref_for(u,image))
    if m.get('voice_binding') and not any(r['usage'].startswith('reference_') for r in refs):refs.append(ref_for('reference_image',image))
    for r in refs:
        if mode=='subjects':r['subject_name']='person'
    b=body(image,m['id'],'image' if m['kind']=='image' else 'video',image_confirmed=True)
    b.update(refs=refs,video_mode=mode,duration=spec.get('durations',m['durations'])[0] if spec.get('durations',m['durations']) else 3,audio_mode=m['audio_options'][0],person_mode='default',resolution=spec.get('resolutions',m['resolutions'])[0])
    return b

def ref_for(u,image):
    if u.endswith('video'):
        return dict(role='motion',usage=u,url='https://materials.example.com/'+uuid.uuid4().hex+'.mp4',vendor_kind='video',duration=4)
    if 'audio' in u:return dict(role='audio',usage=u,url='https://materials.example.com/sound.wav',vendor_kind='audio',duration=4)
    if u in ('element','voice'):return dict(role='look',usage=u,vendor_asset_id='123',vendor_kind=u,vendor_active=True)
    if u in ('file','link'):return dict(role='document',usage=u,url='https://materials.example.com/brief.pdf',vendor_kind=u)
    return dict(role='look' if u in ('first_frame','last_frame') else 'upper',usage=u,url='https://materials.example.com/'+uuid.uuid4().hex+'.png',vendor_kind='image')

@pytest.mark.parametrize('mid,mode',CASES)
def test_each_declared_mode_has_validated_request(lab,image,mid,mode):
    m=catalog.model(mid);b=mode_body(m,mode,image)
    if m['adapter']=='mini_image':
        for r in b['refs']:r['role']='pose'
    b=engine.validate(JobInput(**b).model_dump());b['job_id']='contract-mode'
    req=providers.build_request(m,b,True)
    assert req['method']=='POST' and req['url'].startswith(config.PROVIDERS[m['provider']]['base'])
    assert 'Authorization' not in req['headers']
    encoded=json.dumps(req['body'])
    for r in b['refs']:
        assert (r.get('url') or r.get('vendor_asset_id') or 'asset://'+r['asset_id']) in encoded
    assert len(b['asset_snapshot'])==len(b['refs'])

@pytest.mark.parametrize('mid', ['wan3.0-video','minimax-h3','native-MiniMax-H3-Max','seedance'])
def test_multimodal_not_flat_image(lab,image,mid):
    m=catalog.model(mid);b=mode_body(m,'reference',image)
    b['refs']=[ref_for('reference_image',image),ref_for('reference_video',image),ref_for('reference_audio',image)]
    b=engine.validate(JobInput(**b).model_dump());b['job_id']='multi'
    wire=providers.build_request(m,b,True)['body']
    media=wire['input']['media'] if m['adapter']=='wan3' else wire['content'][1:]
    assert len(media)==3
    assert {x.get('role',x.get('type')) for x in media}=={'reference_image','reference_video','reference_audio'}

def test_channel_specific_h3_max(lab,image):
    assert 'reference' not in catalog.model('tx-minimax-video-h3-max')['modes']
    assert 'reference' in catalog.model('native-MiniMax-H3-Max')['modes']
    b=mode_body(catalog.model('tx-minimax-video-h3-max'),'first_frame',image);b['video_mode']='reference'
    with pytest.raises(ValueError,match='模式'):engine.validate(b)

def test_wrong_video_role_and_image_limit_rejected(lab,image):
    m=catalog.model('wan3.0-video');b=mode_body(m,'first_frame',image)
    b['refs'].append(ref_for('reference_video',image))
    with pytest.raises(ValueError,match='不接收'):engine.validate(b)
    b=mode_body(m,'reference',image);b['refs']=[ref_for('reference_image',image) for _ in range(11)]
    with pytest.raises(ValueError,match='最多'):engine.validate(b)

def test_seedance_trusted_id_no_selfie_bypass(lab,image):
    m=catalog.model('seedance');b=mode_body(m,'first_frame',image);b.update(person_mode='self',identity_consent=True)
    with pytest.raises(ValueError,match='Asset'):engine.validate(b)
    b['refs']=[dict(role='look',usage='first_frame',vendor_kind='image',vendor_asset_id='asset-approved-person',vendor_active=True)]
    b=engine.validate(JobInput(**b).model_dump());b['job_id']='trusted'
    assert providers.build_request(m,b,True)['body']['content'][1]['image_url']['url']=='asset://asset-approved-person'

def test_wan_voice_binding_and_edit(lab,image):
    m=catalog.model('wan2.7-r2v-2026-06-12');b=mode_body(m,'reference',image);b['refs'][0]['voice_url']='https://materials.example.com/voice.mp3'
    b=engine.validate(JobInput(**b).model_dump());b['job_id']='voice'
    media=providers.build_request(m,b,True)['body']['input']['media']
    assert media[0]['reference_voice'].endswith('voice.mp3') and len(media)==1
    m=catalog.model('wan2.7-videoedit');b=engine.validate(JobInput(**mode_body(m,'edit',image)).model_dump());b['job_id']='edit'
    wire=providers.build_request(m,b,True)['body'];assert wire['parameters']['duration']==0 and wire['input']['media'][0]['type']=='video'

def test_input_output_billing_not_output_only(lab,image):
    m=catalog.model('wan3.0-video');b=mode_body(m,'reference',image);b.update(duration=5,resolution='720P')
    b['refs']=[ref_for('reference_video',image)];b['refs'][0]['duration']=4
    quote=engine.estimate(engine.validate(JobInput(**b).model_dump()))
    assert quote['reference_cny']==5.4 and quote['estimated_cny']==0
    assert '输入视频' in ';'.join(quote['breakdown'])

def test_vidu_subjects_groups_are_wire_groups(lab,image):
    m=catalog.model('native-viduq2-pro');b=mode_body(m,'subjects',image)
    b['refs']=[dict(ref_for('subject_image',image),subject_name='person'),dict(ref_for('subject_image',image),subject_name='person'),dict(ref_for('subject_image',image),subject_name='jacket')]
    b=engine.validate(JobInput(**b).model_dump());b['job_id']='groups'
    wire=providers.build_request(m,b,True)['body'];assert 'images' not in wire and len(wire['subjects'])==2 and len(wire['subjects'][0]['images'])==2

def test_yt_post_query_is_read_and_never_submit(lab):
    calls=[]
    def reply(request):
        calls.append(request);return httpx.Response(200,json={'id':'yt1','status':'completed','data':{'url':'https://out.example.com/a.mp4'}})
    r=providers.transport(catalog.model('tx-yt-video'),task_id='yt1',client=httpx.Client(transport=httpx.MockTransport(reply)))
    assert len(calls)==1 and calls[0].method=='POST' and calls[0].url.path.endswith('/query')
    assert r['status']=='succeeded' and r['urls']

def test_hy35_sse_result(lab,image):
    m=catalog.model('tx-hy-image-v3.5-preview');b=engine.validate(JobInput(**mode_body(m,'text',image)).model_dump());b['job_id']='sse'
    frames='data: '+json.dumps({'choices':[{'delta':{'image':{'url':'https://out.example.com/a.png'}}}]})+'\n\ndata: [DONE]\n'
    client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=frames,headers={'content-type':'text/event-stream'})))
    assert providers.transport(m,body=b,client=client)['urls']==['https://out.example.com/a.png']

def test_audio_document_upload_and_kind_validation(lab,image):
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x00\x00'*64000)
    a=assets.save_bytes(buffer.getvalue(),'voice.wav');assert a['kind']=='audio' and a['duration']==4
    d=assets.save_bytes(b'Generate a white-background outfit','brief.txt');assert d['kind']=='file'
    with pytest.raises(ValueError):assets.save_bytes(b'notpdf','brief.pdf')
    m=catalog.model('wan3.0-video');b=mode_body(m,'reference',image);b['refs']=[dict(asset_id=a['id'],role='audio',usage='reference_audio'),ref_for('reference_image',image)]
    assert engine.validate(JobInput(**b).model_dump())['asset_snapshot'][0]['kind']=='audio'

def test_kling_wire_requirements(lab,image):
    m=catalog.model('tx-kling-video-v3-omni');b=mode_body(m,'reference',image)
    b['refs'].append(dict(role='audio',usage='voice',vendor_asset_id='voice-existing',vendor_kind='voice',vendor_active=True));b['audio_mode']='native'
    b=engine.validate(JobInput(**b).model_dump());b['job_id']='omni'
    wire=providers.build_request(m,b,True)['body'];assert wire['settings']['aspect_ratio']=='9:16'
    assert wire['contents'][-1]['id']=='voice2' and wire['contents'][-1]['voice_id']=='voice-existing'
    assert '@voice2' in wire['contents'][0]['text']
    m=catalog.model('native-kling-v3-turbo');b=engine.validate(JobInput(**mode_body(m,'text',image)).model_dump());b['job_id']='turbo'
    req=providers.build_request(m,b,True);assert req['url'].endswith('/text-to-video/kling-3.0-turbo')
    assert 'audio' not in req['body']['settings'] and 'multi_shot' not in req['body']['settings']
    m=catalog.model('tx-kling-image-v3');b=engine.validate(JobInput(**mode_body(m,'text',image)).model_dump());b['job_id']='image'
    assert providers.build_request(m,b,True)['body']['resolution']=='1k'

def test_kling_resolution_constraints(lab,image):
    m=catalog.model('tx-kling-video-v2.5-turbo');b=mode_body(m,'first_last',image)
    assert b['resolution']=='1080p';b['resolution']='720p'
    with pytest.raises(ValueError,match='清晰度'):engine.validate(JobInput(**b).model_dump())
    m=catalog.model('tx-kling-video-v3-omni');b=mode_body(m,'feature',image);b['audio_mode']='original'
    with pytest.raises(ValueError,match='静音'):engine.validate(JobInput(**b).model_dump())
