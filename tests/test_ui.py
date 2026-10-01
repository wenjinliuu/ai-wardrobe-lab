"""Browser acceptance: navigation, responsive layout, mock image→review→video."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
import httpx
import pytest
from playwright.sync_api import sync_playwright,expect

@pytest.fixture(scope='module')
def server(tmp_path_factory):
    s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
    env={**os.environ,'LAB_DEV_MODE':'true','LAB_PASSWORD':'','LAB_SESSION_SECRET':'ui-test-secret-'*4,'LAB_LIVE_ENABLED':'false','LAB_PUBLIC_BASE_URL':'','LAB_DATA_DIR':str(tmp_path_factory.mktemp('ui-data'))}
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url=f'http://127.0.0.1:{port}'
    for _ in range(60):
        try:
            if httpx.get(url+'/healthz',timeout=1).status_code==200:break
        except httpx.HTTPError:pass
        time.sleep(.1)
    else:proc.terminate();raise RuntimeError('Test server did not start')
    yield url
    proc.terminate();proc.wait(timeout=10)

@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        options={'headless':True,'args':['--no-sandbox']}
        if os.getenv('LAB_TEST_CHROME'):options['executable_path']=os.environ['LAB_TEST_CHROME']
        b=p.chromium.launch(**options)
        yield b
        b.close()

def test_desktop_full_mock_flow(browser,server):
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(server);expect(page.locator('main h1')).to_have_text('从一套穿搭，开始探索。')
    page.locator('[data-action="demo"]').click();expect(page.locator('.ref')).to_have_count(3)
    page.locator('[data-field="reference_board"]').check()
    page.locator('[data-action="picker"]').click()
    assert '.png' in page.locator('#upload-input').get_attribute('accept')
    assert page.locator('#upload-input').evaluate('(e)=>e.multiple')
    page.locator('[data-close]').first.click()
    page.locator('[data-field="reference_board"]').uncheck()
    page.locator('[data-action="preview"]').click();expect(page.locator('dialog')).to_be_visible();expect(page.locator('.code')).to_contain_text('/images/generations');page.locator('[data-close]').first.click()
    page.locator('[data-action="generate"]').click();expect(page.locator('#preview-mode')).to_contain_text('已保存',timeout=15000)
    page.locator('#preview-actions [data-job]').click();page.locator('select[name="verdict"]').select_option('pass');page.locator('#review-form button[type="submit"]').click()
    expect(page.locator('#preview-actions [data-video-from]')).to_be_visible();page.locator('#preview-actions [data-video-from]').click()
    expect(page.locator('[data-field="image_confirmed"]')).to_be_checked()
    page.locator('[data-action="generate"]').click();expect(page.locator('#preview-mode')).to_contain_text('已保存',timeout=20000)
    expect(page.locator('#preview-canvas video')).to_be_visible()
    page.wait_for_function("document.querySelector('#preview-canvas video').readyState >= 2")
    page.evaluate("window.previewElement=document.querySelector('#preview-canvas video')")
    page.locator('#main [data-loop]').check()
    assert page.locator('#preview-canvas video').evaluate('(e)=>e.loop')
    page.locator('#main [data-loop]').uncheck()
    assert not page.locator('#preview-canvas video').evaluate('(e)=>e.loop')
    page.locator('#video-scrub').fill('500')
    page.wait_for_function("document.querySelector('#preview-canvas video').currentTime > .5")
    page.wait_for_timeout(3500)
    assert page.evaluate("window.previewElement===document.querySelector('#preview-canvas video')")
    Path('test-results').mkdir(exist_ok=True)
    page.evaluate("document.querySelector('#toasts').replaceChildren()")
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path='test-results/desktop-studio.png',full_page=True)
    for route in ['assets','templates','workflows','jobs','compare','settings']:
        page.locator(f'#nav [data-route="{route}"]').click();expect(page.locator('#page-title')).to_have_text({'assets':'素材库','templates':'模板与提示词','workflows':'技能与工作流','jobs':'测试记录','compare':'结果对比','settings':'平台连接'}[route])
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#nav [data-route="assets"]').click()
    page.locator('#asset-source').select_option('mock_generated')
    expect(page.locator('.asset-grid')).to_contain_text('模拟结果')
    expect(page.locator('.asset-grid')).to_contain_text('选定')
    expect(page.locator('.asset-grid')).to_contain_text('实际文件')
    expect(page.locator('.asset-grid')).to_contain_text('模拟零费用')
    page.screenshot(path='test-results/evaluation-assets.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.wait_for_timeout(350)
    page.screenshot(path='test-results/evaluation-assets-mobile.png',full_page=True)
    page.set_viewport_size({'width':1440,'height':1100})
    page.locator('#nav [data-route="compare"]').click()
    page.locator('#compare-kind').select_option('video')
    expect(page.locator('.compare-card')).to_have_count(1)
    expect(page.locator('.compare-card video')).to_be_visible()
    expect(page.locator('#compare-select')).to_have_count(0)
    expect(page.locator('.result-details')).to_contain_text('模型标识')
    page.locator('#main [data-loop]').check()
    assert page.locator('.compare-card video').evaluate('(e)=>e.loop')
    assert page.locator('#main [data-loop]').bounding_box()['width']<30
    page.locator('.compare-card video').evaluate('(e)=>e.dataset.continuity="kept"')
    page.evaluate('refreshResults(true)')
    assert page.locator('.compare-card video').get_attribute('data-continuity')=='kept'
    page.locator('#compare-kind').select_option('image')
    expect(page.locator('.compare-card img')).to_be_visible()
    page.locator('#compare-kind').select_option('video')
    page.screenshot(path='test-results/evaluation-compare.png',full_page=True)
    page.locator('#nav [data-route="templates"]').click();page.locator('[data-edit-template="new"]').click();page.locator('[name="prompt"]').fill('保持衣服颜色与图案不变，白色背景全身展示。');page.locator('#template-form button[type="submit"]').click();expect(page.locator('main')).to_contain_text('我的新模板')
    assert not errors
    page.close()

def test_mobile_layout(browser,server):
    page=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,device_scale_factor=1)
    page.goto(server);expect(page.locator('main h1')).to_be_visible()
    page.locator('[data-action="demo"]').click();expect(page.locator('.ref')).to_have_count(3)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    Path('test-results').mkdir(exist_ok=True)
    page.evaluate("document.querySelector('#toasts').replaceChildren()")
    page.screenshot(path='test-results/mobile-studio.png',full_page=True)
    page.locator('#menu-toggle').click();page.locator('#nav [data-route="settings"]').click();expect(page.locator('#page-title')).to_have_text('平台连接')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.close()

def test_model_modes_and_material_entries(browser,server):
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(server);expect(page.locator('main h1')).to_be_visible()
    assert page.locator('#f-model_id option').count()>=20
    page.locator('[data-kind="video"]').click()
    for mid,mode in [('wan3.0-video','reference'),('minimax-h3','reference'),('native-MiniMax-H3-Max','reference'),('tx-minimax-video-h3-max','first_last'),('tx-kling-video-v3-omni','edit'),('native-viduq2-pro','subjects'),('seedance','reference')]:
        page.locator('#f-model_id').select_option(mid);page.locator('#f-video_mode').select_option(mode)
        expect(page.locator('.capability-panel')).to_be_visible()
        page.locator('[data-action="external"]').click()
        page.locator('#external-form [name="vendor_kind"]').select_option('image')
        page.locator('#external-form [name="value"]').fill('https://materials.example.com/person.png')
        page.locator('#external-form button[type="submit"]').click();expect(page.locator('.ref')).to_have_count(1)
        assert page.locator('[data-ref-key="usage"] option').count()>=2
        if mode=='subjects':expect(page.locator('[data-ref-key="subject_name"]')).to_be_visible()
        page.locator('[data-remove-ref]').click()
    page.locator('#f-model_id').select_option('tx-minimax-video-h3-max')
    assert page.locator('#f-video_mode option[value="reference"]').count()==0
    assert not errors
    page.close()

def test_first_frame_slots_and_mode_switch(browser,server):
    page=browser.new_page(viewport={'width':1440,'height':1100})
    page.goto(server);expect(page.locator('main h1')).to_be_visible()
    page.locator('[data-kind="video"]').click()
    page.locator('#f-model_id').select_option('tx-minimax-video-h3-max')
    def add_image(number):
        page.locator('[data-action="external"]').click()
        expect(page.locator('[name="vendor_kind"] option')).to_have_count(1)
        page.locator('[name="value"]').fill(f'https://materials.example.com/frame{number}.png')
        page.locator('#external-form button[type="submit"]').click()
    add_image(1)
    expect(page.locator('[data-ref-key="usage"]')).to_have_value('first_frame')
    expect(page.locator('[data-action="external"]')).to_be_disabled()
    expect(page.locator('[data-action="picker"]')).to_be_disabled()
    page.locator('#f-video_mode').select_option('first_last')
    expect(page.locator('[data-action="generate"]')).to_be_disabled()
    page.locator('[data-action="picker"]').click()
    assert not page.locator('#upload-input').evaluate('(e)=>e.multiple')
    page.locator('[data-close]').first.click()
    add_image(2)
    assert page.locator('[data-ref-key="usage"]').evaluate_all('(es)=>es.map(e=>e.value)')==['first_frame','last_frame']
    expect(page.locator('[data-action="external"]')).to_be_disabled()
    page.locator('#f-video_mode').select_option('first_frame')
    expect(page.locator('.ref')).to_have_count(2)
    expect(page.locator('.ref-invalid')).to_have_count(1)
    expect(page.locator('[data-action="generate"]')).to_be_disabled()
    page.locator('[data-remove-ref="1"]').click()
    expect(page.locator('[data-action="generate"]')).to_be_enabled()
    page.locator('#f-video_mode').select_option('text')
    expect(page.locator('.ref')).to_have_count(1)
    expect(page.locator('[data-action="generate"]')).to_be_disabled()
    page.locator('[data-remove-ref]').click()
    expect(page.locator('[data-action="generate"]')).to_be_enabled()
    assert 'adaptive' not in page.locator('#f-ratio option').evaluate_all('(es)=>es.map(e=>e.value)')
    # Both official catalogs remain available despite not configuring their Keys.
    assert page.locator('#f-model_id option[value^="native-vidu"]').count()>0
    assert page.locator('#f-model_id option[value^="native-kling"]').count()>0
    page.screenshot(path='test-results/frame-slots.png',full_page=True)
    page.close()

def test_upload_batch_rejected_before_upload(browser,server):
    page=browser.new_page()
    page.goto(server);expect(page.locator('main h1')).to_be_visible()
    page.locator('[data-kind="video"]').click()
    page.locator('#f-model_id').select_option('tx-minimax-video-h3-max')
    uploads=[]
    page.on('request',lambda r:uploads.append(r.url) if r.method=='POST' and r.url.endswith('/api/assets') else None)
    page.evaluate("uploadFiles([new File(['x'],'a.png'),new File(['y'],'b.png')])")
    expect(page.locator('#toasts')).to_contain_text('名额已满')
    expect(page.locator('.ref')).to_have_count(0)
    assert not uploads
    page.locator('#f-model_id').select_option('wan-animate')
    page.locator('[data-action="external"]').click()
    assert page.locator('[name="vendor_kind"] option').evaluate_all('(es)=>es.map(e=>e.value)')==['image','video']
    page.locator('[name="vendor_kind"]').select_option('video')
    page.locator('[name="value"]').fill('https://materials.example.com/motion.mp4')
    page.locator('#external-form button[type="submit"]').click()
    expect(page.locator('#toasts')).to_contain_text('实际时长')
    expect(page.locator('dialog')).to_be_visible()
    page.locator('[name="duration"]').fill('5')
    page.locator('#external-form button[type="submit"]').click()
    expect(page.locator('[data-ref-key="usage"]')).to_have_value('driving_video')
    expect(page.locator('[data-action="generate"]')).to_be_disabled()
    page.close()

def test_http_uuid_fallback_and_explicit_retry_keeps_id(browser,server):
    page=browser.new_page()
    page.add_init_script("Object.defineProperty(Crypto.prototype,'randomUUID',{value:undefined,configurable:true})")
    page.goto(server);expect(page.locator('main h1')).to_be_visible()
    page.locator('[data-action="demo"]').click();expect(page.locator('.ref')).to_have_count(3)
    page.locator('#f-label').fill('uuid-idempotency-check')
    keys=[]
    def lose_first_response(route):
        keys.append(route.request.headers['idempotency-key'])
        response=route.fetch()
        if len(keys)==1:route.abort('failed')
        else:route.fulfill(response=response)
    page.route('**/api/jobs',lambda route:lose_first_response(route) if route.request.method=='POST' else route.continue_())
    page.locator('[data-action="generate"]').click()
    expect(page.locator('[data-action="generate"]')).to_be_enabled()
    expect(page.locator('#toasts')).to_contain_text('Failed to fetch')
    # No automatic repeat occurs; retry is an explicit second click.
    assert len(keys)==1
    page.locator('[data-action="generate"]').click()
    expect(page.locator('#preview-mode')).to_contain_text('已保存',timeout=15000)
    assert len(keys)==2 and keys[0]==keys[1]
    import re
    assert re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',keys[0])
    records=page.evaluate("fetch('/api/jobs').then(r=>r.json())")
    assert len([j for j in records if j['body']['label']=='uuid-idempotency-check'])==1
    page.close()


def test_receipt_controls_and_no_inferred_units_promoted(browser,server):
    from copy import deepcopy
    from app.billing import reconcile
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(server);expect(page.locator('main h1')).to_be_visible()
    page.locator('[data-action="demo"]').click()
    page.locator('[data-action="generate"]').click()
    expect(page.locator('#preview-mode')).to_contain_text('已保存',timeout=15000)
    jid=page.evaluate('state.activeJob')
    detail=page.evaluate('(id)=>fetch("/api/jobs/"+id).then(r=>r.json())',jid)
    fake=deepcopy(detail);fake['body']['mode']='live';fake['actual']=None
    fake['body']['model_snapshot']['provider']='tokenhub'
    fake['billing_context'].update(unit='tokens',rate=10,rate_basis=1000000,verification='official',date='2026-10-01')
    fake['body']['billing_snapshot']=fake['billing_context']
    submitted=[]
    def intercept(route):
        if route.request.method=='GET':route.fulfill(json=fake)
        elif route.request.url.endswith('/billing-preview'):
            try:route.fulfill(json=reconcile(fake['body'],route.request.post_data_json))
            except ValueError as e:route.fulfill(status=422,json={'detail':str(e)})
        elif route.request.url.endswith('/review'):
            submitted.append(route.request.post_data_json);route.fulfill(json={'ok':True})
        else:route.continue_()
    page.route('**/api/jobs/'+jid+'**',intercept)
    page.locator('#preview-actions [data-job]').click()
    expect(page.locator('.billing-panel')).to_be_visible()
    page.locator('[name="actual_cny"]').fill('1.98')
    expect(page.locator('[name="billed_units"]')).to_have_value('198000')
    expect(page.locator('#billing-calculation')).to_contain_text('非实测')
    page.locator('[name="billing_mode"]').select_option('units')
    expect(page.locator('[name="billed_units"]')).to_have_value('')
    page.locator('[name="billed_units"]').fill('300000')
    expect(page.locator('[name="actual_cny"]')).to_have_value('3')
    assert page.locator('[name="actual_cny"]').evaluate('(e)=>e.readOnly')
    page.locator('[name="billing_mode"]').select_option('both')
    expect(page.locator('[name="actual_cny"]')).to_have_value('')
    page.locator('[name="actual_cny"]').fill('2.4')
    expect(page.locator('#billing-calculation')).to_contain_text('账单差额 ¥-0.6')
    Path('test-results').mkdir(exist_ok=True)
    page.screenshot(path='test-results/evaluation-billing.png',full_page=True)
    page.locator('#review-form button[type="submit"]').click()
    expect(page.locator('#dialog')).not_to_be_visible()
    assert len(submitted)==1
    assert submitted[0]['actual_cny']==2.4 and submitted[0]['billed_units']==300000
    assert submitted[0]['billing_mode']=='both' and submitted[0]['motion'] is None
    assert not errors
    page.close()
