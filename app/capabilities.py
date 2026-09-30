"""Validate material roles against a particular channel, model and input mode."""
import hashlib,json,re
from collections import Counter,defaultdict
from urllib.parse import urlsplit
from . import catalog,config,db,contracts

def external_url(url):
    u=urlsplit(url)
    # Passed to provider only, never fetched by this server. Provider must be able to reach it.
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.fragment:raise ValueError('外部素材/网页请使用完整HTTPS公网URL')
    return url

def validate(b,m,t):
    mode=b.get('video_mode','auto');mode=m['default_mode'] if mode=='auto' else mode
    if mode not in m['modes']:raise ValueError('当前渠道/模型不支持这个输入模式')
    b['video_mode']=mode;spec=m['modes'][mode];refs=b['refs'];snap=[];counts=Counter();seen=set()
    if len(refs)>m.get('total_refs',50):raise ValueError('素材总数超过模型限制')
    board=b['reference_board']
    if board and b['kind']!='image':raise ValueError('参考板只能用于图像对照，不能直接作为视频首帧')
    for r in refs:
        if r['role'] not in catalog.ROLES:raise ValueError('未知素材角色')
        sources=[r.get('asset_id'),r.get('vendor_asset_id'),r.get('url')]
        if sum(bool(x) for x in sources)!=1:raise ValueError('每个素材需要且只能选择本地文件、供应商ID、外部URL之一')
        identity=next(x for x in sources if x)
        if identity in seen:raise ValueError('同一素材不能重复引用')
        seen.add(identity)
        if r.get('asset_id'):
            a=db.get_asset(r['asset_id']);kind=a['kind']
            metadata={k:a[k] for k in ('id','sha256','width','height','duration','size','kind')}
            if kind=='image':
                if min(a['width'],a['height'])<m['min_side'] or max(a['width'],a['height'])>m['max_side'] or a['size']>m['max_mb']*1024*1024:raise ValueError(a['name']+'不符合图片尺寸或大小限制')
                if not m.get('ratio_min',0)<=a['width']/a['height']<=m.get('ratio_max',100):raise ValueError('图片宽高比超出模型范围')
            elif kind=='file':
                if a['size']>m.get('file_mb',100)*1024*1024:raise ValueError('文档超过100MB限制')
            elif kind in ('video','audio'):
                if not m.get(kind+'_min') or not m[kind+'_min']<=a['duration']<=m[kind+'_max']:raise ValueError(kind+'时长不符合模型要求')
                if a['size']>m[kind+'_mb']*1024*1024:raise ValueError(kind+'文件过大')
                if kind=='video' and (min(a['width'],a['height'])<m['video_side_min'] or max(a['width'],a['height'])>m['video_side_max']):raise ValueError('视频尺寸超出模型范围')
                details=json.loads(a.get('details') or '{}')
                if kind=='video' and details.get('fps'):
                    if not m.get('video_fps_min',0)<=details['fps']<=m.get('video_fps_max',120):raise ValueError('视频帧率不符合模型要求')
            parent=db.get_job(a['source']) if r['role']=='look' else None
            if parent and b['kind']=='video':
                if json.loads(parent['review'] or '{}').get('verdict')!='pass':raise ValueError('生成图需评为合格后才能做视频')
                if b['mode']=='live' and json.loads(parent['body'])['mode']=='mock':raise ValueError('模拟结果不能用于真实生成')
        else:
            kind=r.get('vendor_kind','image')
            if r.get('url'):external_url(r['url'])
            if r.get('vendor_asset_id'):
                if m['provider']=='ark':
                    if not r['vendor_asset_id'].startswith('asset-') or not r.get('vendor_active'):raise ValueError('方舟授权Asset需要有效asset- ID并确认Active状态')
                elif m['provider']=='minimax' and m['adapter']=='h3':
                    if not r['vendor_asset_id'].startswith('mm_file://'):raise ValueError('MiniMax已有文件请填mm_file://文件ID')
                elif m['provider']=='dashscope' and m['adapter'] in ('wan_media','wan3'):
                    if not r['vendor_asset_id'].startswith('ark_asset_'):raise ValueError('百炼资产请填写资产中心ark_asset_ ID')
                elif kind in ('element','voice') and m['provider'] in ('kling','tokenhub'):
                    if not m.get('element_limit') and kind=='element':raise ValueError('该模型尚未开放元素ID输入')
                else:raise ValueError('该渠道未接入此类供应商资产ID，请上传文件或用公网URL')
            metadata={'id':identity,'sha256':hashlib.sha256(identity.encode()).hexdigest(),'kind':kind,'duration':r.get('duration'),'width':None,'height':None,'size':None,'external':True}
            if kind in ('video','audio') and not r.get('duration'):raise ValueError('外部视频/音频需要填写实际时长，用于限制校验和费用预估')
            if kind in ('video','audio') and m.get(kind+'_min') and not m[kind+'_min']<=r['duration']<=m[kind+'_max']:raise ValueError('外部素材时长超出模型要求')
        u=contracts.usage(r,mode,kind);r['usage']=u;r['kind']=kind
        expected='video' if u.endswith('video') else 'audio' if 'audio' in u else 'image' if u.endswith('image') or u in ('first_frame','last_frame') else u
        if kind!=expected:raise ValueError(f'{catalog.USAGES.get(u,u)}需要{expected}素材')
        if u not in spec['limits']:raise ValueError(f'当前模式不接收{catalog.USAGES.get(u,u)}')
        counts[u]+=1
        if r.get('voice_url'):
            if not m.get('voice_binding') or u not in ('reference_image','reference_video'):raise ValueError('只有万相R2V的参考图/视频可单独绑定音色')
            external_url(r['voice_url'])
        if m.get('restricted_identity') and r.get('asset_id') and r['role']=='look':
            parent=db.get_job(db.get_asset(r['asset_id'])['source'])
            if parent:
                pb=json.loads(parent['body'])
                if pb.get('person_mode')=='self' or any(x['role']=='identity' for x in pb['refs']):raise ValueError('已知本人生成图需要通过方舟可信授权素材入口，不能用本地改写图绕过授权')
        if r['role']=='identity' and not b['identity_consent']:raise ValueError('本人参考需要明确确认授权')
        if m.get('restricted_identity') and b['person_mode']=='self' and r['role'] in ('identity','pose','look','motion') and not (r.get('vendor_asset_id') or r.get('url') and r.get('trusted_original')):raise ValueError('Seedance本人素材须使用授权Asset ID或符合方舟信任条件的原始产物URL')
        metadata.update(role=r['role'],usage=u);snap.append(metadata)
    if counts['file'] and counts['link']:raise ValueError('万相3.0文档与网页不能同时输入')
    effective=Counter(reference_image=1) if board else counts
    for u,n in effective.items():
        if n>spec['limits'].get(u,0):raise ValueError(f'{catalog.USAGES.get(u,u)}最多{spec["limits"].get(u,0)}个')
    for u,n in spec.get('required',{}).items():
        if counts[u]<n:raise ValueError(f'需要{n}个{catalog.USAGES.get(u,u)}')
    if m.get('voice_binding') and not counts['reference_image']+counts['reference_video']:raise ValueError('R2V至少需要一件参考图或视频，首帧不能独立使用')
    if spec.get('require_any') and not refs:raise ValueError('参考模式至少需要一件素材')
    if board and any(not r.get('asset_id') or r['kind']!='image' for r in refs):raise ValueError('参考板仅接受本地图片')
    if b['kind']=='video' and mode in ('first_frame','first_last','motion','audio_drive'):
        if any(r['role'] not in ('look','identity','pose') and r.get('usage')=='first_frame' for r in refs):raise ValueError('首帧请使用完整穿搭图；单品图应选择原生参考模式')
        if not b['image_confirmed']:raise ValueError('请确认首帧穿搭图用于视频')
    if b['person_mode']=='self' and not b['identity_consent']:raise ValueError('本人素材需要确认授权')
    if b['resolution'] not in m['resolutions']:raise ValueError('清晰度不支持')
    durations=spec.get('durations',m['durations'])
    if durations and b['duration'] not in durations:raise ValueError('时长不支持')
    if b['ratio'] not in m['ratios']:raise ValueError('画幅不支持')
    opts=m.get('audio_options',['off'])
    if b.get('audio_mode','off') not in opts:
        if b.get('audio_mode','off')=='off' and opts==['native']:b['audio_mode']='native'
        else:raise ValueError('声音模式不支持')
    # Constraints depending on material combinations, not just per-slot maxima.
    for k in ('video','audio'):
        total=sum(x.get('duration') or 0 for x in snap if x['kind']==k)
        if total>m.get(k+'_total',10000):raise ValueError(k+'素材总时长超过上限')
    ni=sum(x['kind']=='image' for x in snap);nv=sum(x['kind']=='video' for x in snap);seconds=sum(x.get('duration') or 0 for x in snap if x['kind']=='video')
    if mode=='reference' and counts['reference_audio'] and not ni+nv:raise ValueError('参考音频需搭配图片或视频，不能单独用于参考生视频')
    if m.get('max_visual_refs') and counts['reference_image']+counts['reference_video']>m['max_visual_refs']:raise ValueError('图片与视频参考合计超过5个')
    if m['adapter']=='wan3' and seconds+b['duration']>30:raise ValueError('输入视频加输出时长不得超过30秒')
    if m['adapter']=='wan_media' and nv and 'r2v' in m['model'] and b['duration']>10:raise ValueError('万相R2V有视频参考时输出最长10秒')
    if m['adapter']=='mini_old' and b['resolution']=='1080P' and b['duration']!=6:raise ValueError('1080P只支持6秒')
    if m['adapter']=='wan_image' and b['resolution']=='4K' and refs:raise ValueError('万相4K仅文生图，不支持参考图')
    if m['adapter']=='tx_pixverse' and 'v5.6' in m['model'] and b['resolution']=='1080p' and b['duration']==10:raise ValueError('V5.6的1080p不支持10秒')
    if 'kling' in m['adapter']:
        if ni+counts['element']>m.get('max_combined_refs',spec['limits'].get('reference_image',m['max_images'])):
            if mode in ('reference','feature','edit'):raise ValueError('参考图与元素合计超出模式限制')
        if mode in ('edit','feature') and b.get('audio_mode')=='native':raise ValueError('可灵带输入视频时请选择静音或保留原声')
        if 'v2-6' in m['model'] or 'v2.6' in m['model']:
            if b.get('audio_mode')=='native' and b['resolution']=='720p':raise ValueError('可灵2.6原生音频仅1080p')
    if m['adapter'] in ('vidu','tx_vidu'):
        if nv and (ni>4 or nv==2 and any(x['duration']>5 for x in snap if x['kind']=='video')):raise ValueError('Vidu两段视频各最多5秒，带视频图片最多4张')
        if mode=='subjects':
            groups=defaultdict(list)
            for r in refs:
                if not r.get('subject_name'):raise ValueError('每件主体素材请填写分组名称')
                groups[r['subject_name']].append(r)
            if len(groups)>7:raise ValueError('主体分组最多7组')
            for rs in groups.values():
                if len(rs)>3 or len({r['kind'] for r in rs})>1:raise ValueError('每个主体只能1～3图或1段视频，不能混用')
                if rs[0]['kind']=='video' and (len(rs)>1 or next(x['duration'] for x in snap if x['id']==(rs[0].get('asset_id') or rs[0].get('url') or rs[0].get('vendor_asset_id')))>5):raise ValueError('主体视频最多1段5秒')
    if m.get('requires_workspace') and b['mode']=='live' and not urlsplit(config.PROVIDERS['dashscope']['base']).hostname.endswith('.cn-beijing.maas.aliyuncs.com'):raise ValueError('此模型需要北京工作空间端点，请设置DASHSCOPE_BASE_URL=https://工作空间ID.cn-beijing.maas.aliyuncs.com')
    if m['adapter']=='mini_image' and any(r['role'] not in ('identity','pose','look') for r in refs):raise ValueError('MiniMax Image参考只用于人物主体，请使用人物图；不支持服装多图编辑')
    if m['adapter']=='h3' and mode=='text' and b['ratio']=='adaptive':raise ValueError('H3纯文字模式需要明确画幅')
    if b['mode']=='live':
        inline_bytes=sum(db.get_asset(r['asset_id'])['size'] for r in refs if r.get('asset_id') and r['kind']=='image') if m.get('inline_images',True) and not config.PUBLIC_BASE.startswith('https://') else 0
        if inline_bytes*4/3>m.get('body_mb',64)*1024*1024:raise ValueError('Base64请求体超过模型上限，请使用公网URL或减少素材大小')
        if not config.LIVE or not config.key(m['provider']):raise ValueError('真实调用未开启或服务器尚未配置平台Key')
        if not b['paid_confirmed'] or b['max_cost']<=0:raise ValueError('请确认付费并填写预算')
        if m.get('verified')!='contract_tested':raise ValueError('模型尚未通过接口契约测试')
    prompt=b['prompt_override'] or t['prompt']
    if t.get('negative_prompt'):prompt+='\n避免：'+t['negative_prompt']
    lines=[];seq=Counter()
    for r in refs:
        seq[r['kind']]+=1;name={'image':'图','video':'视频','audio':'音频'}.get(r['kind'],'素材')+str(seq[r['kind']])
        if m['adapter'] in ('native_kling_omni',):name='<<<'+r['kind']+'_'+str(seq[r['kind']])+'>>>'
        elif m['adapter']=='tx_pixverse':name='@ref'+str(seq[r['kind']])
        lines.append(name+'='+catalog.ROLES[r['role']]+'（'+catalog.USAGES[r['usage']]+'）')
    if lines:prompt+='\n素材说明：'+'；'.join(lines)
    if board:prompt+='。素材在单张参考板内按编号排列；输出完整照片，不能包含参考板或编号。'
    if m['prompt_max'] and len(prompt)>m['prompt_max']:raise ValueError('提示词加素材说明超过模型字符限制')
    b.update(compiled_prompt=prompt if m['prompt_max'] else '',asset_snapshot=snap,model_snapshot=dict(m,query_mode=mode),template_snapshot=t,workflow_version='2.0.0',prompt_version=f"{t['id']}@{t['version']}"+('+override' if b['prompt_override'] else ''))
    return b
