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
    page.locator('[data-action="preview"]').click();expect(page.locator('dialog')).to_be_visible();expect(page.locator('.code')).to_contain_text('/images/generations');page.locator('[data-close]').first.click()
    page.locator('[data-action="generate"]').click();expect(page.locator('#preview-mode')).to_contain_text('已保存',timeout=15000)
    page.locator('#preview-actions [data-job]').click();page.locator('select[name="verdict"]').select_option('pass');page.locator('#review-form button[type="submit"]').click()
    expect(page.locator('#preview-actions [data-video-from]')).to_be_visible();page.locator('#preview-actions [data-video-from]').click()
    expect(page.locator('[data-field="image_confirmed"]')).to_be_checked()
    page.locator('[data-action="generate"]').click();expect(page.locator('#preview-mode')).to_contain_text('已保存',timeout=20000)
    expect(page.locator('#preview-canvas video')).to_be_visible()
    page.wait_for_function("document.querySelector('#preview-canvas video').readyState >= 2")
    page.evaluate("window.previewElement=document.querySelector('#preview-canvas video')")
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
