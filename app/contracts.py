"""Model-specific wire contracts. Pure builders, without credentials or network."""
from collections import defaultdict
from math import sqrt, floor
from . import config

def usage(r, mode, kind=None):
    if r.get('usage','auto')!='auto':return r['usage']
    kind=kind or r.get('kind') or r.get('vendor_kind') or ('video' if r['role']=='motion' else 'image')
    if kind in ('element','voice','file','link'):return kind
    if mode=='subjects':return 'subject_'+kind
    if kind=='video':return {'motion':'driving_video','motion_subject':'driving_video','feature':'feature_video','edit':'base_video','extend':'first_video'}.get(mode,'reference_video')
    if kind=='audio':return 'driving_audio' if mode in ('audio_drive','extend','first_frame','first_last') else 'reference_audio'
    return 'first_frame' if mode in ('first_frame','first_last','motion','audio_drive') else ('last_frame' if mode=='last_frame' else 'reference_image')

def image_size(res,ratio,sep='x'):
    if '*' in res or 'x' in res:return res.replace('*',sep).replace('x',sep)
    side={'1K':1024,'1.5K':1536,'2K':2048,'3K':3072,'4K':4096,'1024':1024}.get(res,1024)
    w,h=map(int,('1:1' if ratio=='adaptive' else ratio).split(':'))
    # Preserve the priced pixel area for portrait and landscape ratios.
    width=max(256,floor(sqrt(side*side*w/h)/16)*16)
    height=max(256,floor(sqrt(side*side*h/w)/16)*16)
    return sep.join(map(str,(width,height)))

def build(m,b,uri):
    a=m['adapter'];mode=b.get('video_mode','auto');mode=m['default_mode'] if mode=='auto' else mode
    refs=b['refs'];refs=[dict(r,usage=usage(r,mode)) for r in refs]
    get=lambda u:[r for r in refs if r['usage']==u]
    images=[r for r in refs if r['usage'] in ('first_frame','last_frame','reference_image','subject_image')]
    videos=[r for r in refs if r['usage'].endswith('video')]
    prompt=b['compiled_prompt'];res=b['resolution'];dur=b['duration'];ratio=b['ratio'];audio=b.get('audio_mode','off')
    body={'model':m['model']};headers={'Content-Type':'application/json'};path=''
    u=lambda r:uri(r,m.get('inline_images',True))
    first=lambda k:u(get(k)[0])
    if a in ('seedream','tx_seedream'):
        path='/images/generations' if a=='seedream' else '/v1/wand/si-image/generation'
        body.update(prompt=prompt,size=res,response_format='url',watermark=True)
        if images:body['image' if a=='seedream' else 'images']=[u(r) for r in images]
        if m.get('sequential') or a=='seedream' and 'lite' in m['model']:body['sequential_image_generation']='disabled'
    elif a in ('qwen','wan_image'):
        path='/api/v1/services/aigc/multimodal-generation/generation'
        body.update(input={'messages':[{'role':'user','content':[*[{'image':u(r)} for r in images],{'text':prompt}]}]},parameters={'n':1,'size':res,'watermark':True,'prompt_extend':False})
        if a=='wan_image':body['parameters'].pop('prompt_extend',None)
    elif a in ('wan3','wan_media'):
        path='/api/v1/services/aigc/video-generation/video-synthesis';headers['X-DashScope-Async']='enable'
        media=[]
        for r in refs:
            item={'type':{'base_video':'video','first_video':'first_clip'}.get(r['usage'],r['usage']),'url':u(r)}
            if r.get('voice_url'):item['reference_voice']=r['voice_url']
            media.append(item)
        params={'resolution':res,'duration':0 if mode=='edit' else dur,'watermark':True,'prompt_extend':False,'seed':b['seed']}
        if ratio!='adaptive':params['ratio']=ratio
        if a=='wan3':params['audio']=audio!='off'
        elif mode=='edit':params['audio_setting']='origin' if audio=='original' else 'auto'
        body.update(input={'prompt':prompt,'media':media},parameters=params)
    elif a in ('h3','tx_wand_video','seedance'):
        path={'h3':'/v2/video_generation' if m['provider']=='minimax' else '/v1/wand/minimax-video-v2/generation','tx_wand_video':'/v1/wand/vega-videos/tasks','seedance':'/contents/generations/tasks'}[a]
        content=[{'type':'text','text':prompt}]
        for r in refs:
            k='video' if r['usage'].endswith('video') else 'audio' if 'audio' in r['usage'] else 'image'
            content.append({'type':k+'_url',k+'_url':{'url':u(r)},'role':r['usage']})
        body.update(content=content,resolution=res,duration=dur,ratio='adaptive' if a=='h3' and mode in ('first_frame','last_frame','first_last') else ratio)
        if a=='seedance':body.update(generate_audio=audio=='native',watermark=True,seed=b['seed'])
        else:body['aigc_watermark']=True
    elif a=='mini_old':
        path='/v1/video_generation' if m['provider']=='minimax' else '/v1/wand/minimax-video/generation'
        body.update(prompt=prompt,resolution=res,duration=dur,prompt_optimizer=False)
        if images:body['first_frame_image']=u(images[0])
        if m['provider']=='tokenhub':body['aigc_watermark']=True
    elif a in ('kling','kling_motion','kling_omni','native_kling_standard'):
        if a=='native_kling_standard':path=m.get('native_text_path') if mode=='text' else m['native_path'];body={}
        else:path='/v1/wand/kling/'+('motion-control' if a=='kling_motion' else 'omni-video' if a=='kling_omni' else 'text-to-video' if mode=='text' else 'image-to-video')
        contents=[{'type':'prompt','text':prompt}]
        for r in refs:
            typ={'first_frame':'image','driving_video':'video'}.get(r['usage'],r['usage']) if a=='kling_motion' else {'reference_image':'refer_image'}.get(r['usage'],r['usage'])
            contents.append({'type':typ,**({'id':f'{typ}{len(contents)}'} if typ in ('element','voice') else {}),**({'element_id':r['vendor_asset_id']} if typ=='element' else {'voice_id':r['vendor_asset_id']} if typ=='voice' else {'url':u(r)})})
        settings={'resolution':res,'audio':audio,'duration':dur,'multi_shot':mode=='feature' and 'v3' in m['model']}
        if a=='kling_omni' or a in ('kling','native_kling_standard') and mode=='text':settings['aspect_ratio']=ratio
        if 'v3-turbo' in m['model']:settings.pop('audio',None);settings.pop('multi_shot',None)
        elif a=='kling' and m['model']!='kling-video-v3':settings.pop('multi_shot',None)
        if a=='kling_motion':settings.pop('duration');settings.pop('multi_shot');settings['character_orientation']='video'
        if mode=='edit':settings.pop('duration',None)
        body.update(contents=contents,settings=settings,options={'external_task_id':b['job_id'],'watermark_info':{'enabled':True}})
    elif a=='native_kling_legacy':
        path='/v1/videos/'+('text2video' if mode=='text' else 'image2video')
        body={'model_name':m['model'],'prompt':prompt,'duration':str(dur),'mode':{'720p':'std','1080p':'pro','4k':'4k'}[res],'sound':'on' if audio=='native' else 'off','external_task_id':b['job_id'],'watermark_info':{'enabled':True}}
        if images:body['image']=u(images[0])
        if get('last_frame'):body['image_tail']=first('last_frame')
        if mode=='text':body['aspect_ratio']=ratio
    elif a=='native_kling_motion':
        path='/v1/videos/motion-control';body={'model_name':m['model'],'image_url':first('first_frame'),'video_url':first('driving_video'),'prompt':prompt,'mode':'std' if res=='720p' else 'pro','character_orientation':'video','keep_original_sound':'yes' if audio=='original' else 'no','watermark_info':{'enabled':True}}
    elif a=='native_kling_omni':
        path='/v1/videos/omni-video';body={'model_name':m['model'],'prompt':prompt,'duration':str(dur),'mode':{'720p':'std','1080p':'pro','4k':'4k'}[res],'sound':'on' if audio=='native' else 'off','aspect_ratio':ratio,'external_task_id':b['job_id'],'watermark_info':{'enabled':True}}
        if images:body['image_list']=[{'image_url':u(r),**({'type':'first_frame' if r['usage']=='first_frame' else 'end_frame'} if r['usage'] in ('first_frame','last_frame') else {})} for r in images]
        if get('element'):body['element_list']=[{'element_id':r['vendor_asset_id']} for r in get('element')]
        if mode=='feature' and 'v3' in m['model']:body.update(multi_shot=True,shot_type='intelligence')
        if videos:body['video_list']=[{'video_url':u(r),'refer_type':'base' if mode=='edit' else 'feature','keep_original_sound':'yes' if audio=='original' else 'no'} for r in videos]
    elif a in ('vidu','tx_vidu'):
        name={'text':'text2video','first_frame':'img2video','first_last':'start-end2video','reference':'reference2video','subjects':'reference2video'}[mode]
        path='/ent/v2/'+name if a=='vidu' else '/v1/wand/vidu/'+{'text2video':'text-to-video','img2video':'image-to-video','start-end2video':'start-end-to-video','reference2video':'reference-to-video'}[name]
        body.update(prompt=prompt,duration=dur,resolution=res,seed=b['seed'],aspect_ratio=ratio)
        if mode=='subjects':
            groups=defaultdict(list)
            for r in refs:groups[r['subject_name']].append(r)
            subjects=[]
            for name,rs in groups.items():
                sub={'name':name}
                for k in ('image','video'):
                    selected=[r for r in rs if r['usage']=='subject_'+k]
                    if selected:sub[k+'s']=[u(r) for r in selected]
                voice=next((r.get('voice_id') for r in rs if r.get('voice_id')),None)
                if voice:sub['voice_id']=voice
                subjects.append(sub)
            body['subjects']=subjects
        else:
            if images:body['images']=[u(r) for r in images]
            if videos:body['videos']=[u(r) for r in videos]
        body['audio']=audio=='native'
        if audio=='native':body['audio_type']='all'
    elif a=='tx_pixverse':
        path='/v1/wand/pixverse/'+{'text':'text-to-video','first_frame':'image-to-video','first_last':'start-end-to-video','reference':'reference-to-video'}[mode]
        body.update(prompt=prompt,duration=dur,quality=res,seed=b['seed'],generate_audio_switch=audio=='native')
        if mode=='first_frame':body['img_id']=first('first_frame')
        elif mode=='first_last':body.update(first_frame_img=first('first_frame'),last_frame_img=first('last_frame'))
        elif mode=='reference':body['image_references']=[{'img_id':u(r),'type':'background' if r['role']=='background' else 'subject','ref_name':f'ref{i+1}'} for i,r in enumerate(images)]
        if mode in ('text','reference'):body['aspect_ratio']=ratio
    elif a=='tx_hy_video':
        path='/v1/wand/hunyuan-video/generation';body.update(prompt=prompt,resolution=res,duration=5)
        if images:body['image_url']=u(images[0])
        else:body['aspect_ratio']=ratio
    elif a=='tx_yt':
        path='/v1/api/video/submit';body.update(prompt=prompt,resolution=res,logo_add=1)
        if mode=='audio_drive':body.update(image_url=first('first_frame'),audio_url=first('driving_audio'))
        else:body['image']={'url':first('first_frame')}
    elif a in ('tx_hy_image','tx_hy35'):
        path='/v1/wand/hunyuan-image/'+('v3-generation' if a=='tx_hy_image' else 'v35-generation')
        body.update(size=image_size(res,ratio),seed=b['seed'])
        if a=='tx_hy_image':body.update(prompt=prompt,images=[u(r) for r in images],revise=False,footnote='AI generated')
        else:body.update(session=b['job_id'],messages=[{'role':'user','content':[{'type':'text','text':prompt},*[{'type':'image_url','image_url':{'url':u(r)}} for r in images]]}],use_search_tool=False)
    elif a=='tx_wand_image':
        path='/v1/wand/vega-images/generations';body.update(prompt=prompt,size=image_size(res,ratio))
        if images:body['input']=[{'content':[{'type':'input_image','image_url':u(r)} for r in images]}]
    elif a=='tx_vidu_image':
        path='/v1/wand/vidu-image/generation';body.update(prompt=prompt,images=[u(r) for r in images],resolution=res,aspect_ratio=ratio)
    elif a in ('tx_kling_image','native_kling_image'):
        single=m.get('native_single');native=a=='native_kling_image';path='/v1/images/'+('generations' if single else 'omni-image') if native else '/v1/wand/kling-image/generation'
        if native:body={'model_name':{'kling-image-v3':'kling-v3','kling-image-o1':'kling-image-o1','kling-image-v3-omni':'kling-v3-omni'}[m['model']]}
        body.update(prompt=prompt,n=1,resolution=res.lower(),aspect_ratio=ratio)
        if images:
            if single:body['image']=u(images[0])
            else:body['image_list']=[{'image':u(r)} for r in images] if native else [u(r) for r in images]
        if get('element'):body['element_list']=[{'element_id':r['vendor_asset_id']} for r in get('element')]
    elif a=='mini_image':
        path='/v1/image_generation';body.update(prompt=prompt,n=1,aspect_ratio=ratio,response_format='url',prompt_optimizer=False)
        if images:body['subject_reference']=[{'type':'character','image_file':u(r)} for r in images]
    else:return None
    # Native legacy Kling expects raw base64, rather than a data URI.
    if a.startswith('native_kling') or a=='tx_kling_image':
        def strip(v):
            if isinstance(v,str) and v.startswith('data:'):return v.split(',',1)[1]
            if isinstance(v,list):return [strip(x) for x in v]
            if isinstance(v,dict):return {k:strip(x) for k,x in v.items()}
            return v
        body=strip(body)
    return {'method':'POST','url':config.PROVIDERS[m['provider']]['base'].rstrip('/')+path,'headers':headers,'body':body}
