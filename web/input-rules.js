'use strict';
// Selection checks are shared by every entry path. The server remains authoritative.
(function(root){
  const kindOfUsage=u=>u.endsWith('video')?'video':u.includes('audio')?'audio':u.endsWith('image')||['first_frame','last_frame'].includes(u)?'image':u;
  function usage(r,mode,kind){
    if(r.usage&&r.usage!=='auto')return r.usage;
    if(['element','voice','file','link'].includes(kind))return kind;
    if(mode==='subjects')return 'subject_'+kind;
    if(kind==='video')return ({motion:'driving_video',motion_subject:'driving_video',feature:'feature_video',edit:'base_video',extend:'first_video'})[mode]||'reference_video';
    if(kind==='audio')return ['first_frame','first_last','audio_drive','extend'].includes(mode)?'driving_audio':'reference_audio';
    return ['first_frame','first_last','motion','audio_drive'].includes(mode)?'first_frame':mode==='last_frame'?'last_frame':'reference_image';
  }
  const source=r=>r.asset_id||r.vendor_asset_id||r.url;
  const spec=(m,d)=>m.modes[d.video_mode==='auto'?m.default_mode:d.video_mode]||{limits:{}};
  const material=(r,resolve)=>r.asset_id?resolve(r.asset_id)||{kind:'unknown'}:{...r,kind:r.vendor_kind||'image'};
  const board=d=>d.kind==='image'&&d.reference_board;
  function check(m,d,resolve,labels={}){
    const s=spec(m,d),counts={},errors=[],missing=[],items=d.refs.map((r,i)=>{const a=material(r,resolve);return {r,a,i,u:usage(r,d.video_mode,a.kind)}});
    const name=u=>labels[u]||u;
    const fail=(message,index=null)=>errors.push({message,index});
    const seen=new Set();
    for(const {r,a,i,u} of items){
      if(seen.has(source(r)))fail('同一素材不能重复加入',i);seen.add(source(r));
      counts[u]=(counts[u]||0)+1;
      if(board(d)) {if(!(s.limits.reference_image>0))fail('当前模式不接收参考板',i);if(!r.asset_id||a.kind!=='image')fail('参考板仅接受本地图片',i);}
      else if(!(s.limits[u]>0)||kindOfUsage(u)!==a.kind)fail('当前模式不接收这项素材用途或类型',i);
      else if(counts[u]>s.limits[u])fail(`${name(u)}最多 ${s.limits[u]} 件`,i);
      if(d.refs.length>(m.total_refs||50))fail('素材总数超过模型限制',i);
      if(a.kind==='image'&&a.width&&a.height){
        if(Math.min(a.width,a.height)<m.min_side||Math.max(a.width,a.height)>m.max_side||a.size>m.max_mb*1048576)fail('图片尺寸或大小不符合模型要求',i);
        if(a.width/a.height<(m.ratio_min||0)||a.width/a.height>(m.ratio_max||100))fail('图片宽高比超出模型范围',i);
      }
      if(['video','audio'].includes(a.kind)){
        if(!a.duration)fail('请填写视频或音频的实际时长',i);
        else if(m[a.kind+'_min']&&(a.duration<m[a.kind+'_min']||a.duration>m[a.kind+'_max']))fail('素材时长超出模型范围',i);
        if(a.size>m[a.kind+'_mb']*1048576)fail('素材文件过大',i);
        if(a.kind==='video'&&a.width&&(Math.min(a.width,a.height)<m.video_side_min||Math.max(a.width,a.height)>m.video_side_max))fail('视频尺寸超出模型范围',i);
      }
      if(a.kind==='file'&&a.size>(m.file_mb||100)*1048576)fail('文档文件过大',i);
      if(r.url){try{const url=new URL(r.url);if(url.protocol!=='https:'||url.username||url.password||url.hash)throw Error();}catch{fail('外部素材需要完整 HTTPS URL',i);}}
      if(d.kind==='video'&&u==='first_frame'&&!['look','identity','pose'].includes(r.role))fail('首帧需要完整穿搭图，请调整素材角色',i);
      if(m.adapter==='mini_image'&&!['look','identity','pose'].includes(r.role))fail('此模型的参考图仅支持人物主体',i);
    }
    for(const [u,n] of Object.entries(s.required||{}))if((counts[u]||0)<n)missing.push(`还需要 ${n-(counts[u]||0)} 件${name(u)}`);
    if(s.require_any&&!items.length)missing.push('请添加至少一件参考素材');
    const images=items.filter(x=>x.a.kind==='image'),videos=items.filter(x=>x.a.kind==='video');
    if(counts.file&&counts.link)fail('文档与网页不能同时输入');
    if(m.max_visual_refs&&(counts.reference_image||0)+(counts.reference_video||0)>m.max_visual_refs)fail(`图片与视频参考合计最多 ${m.max_visual_refs} 件`);
    if(m.adapter.includes('kling')&&['reference','feature','edit'].includes(d.video_mode)&&images.length+(counts.element||0)>(m.max_combined_refs||s.limits.reference_image||m.max_images))fail('图片与元素合计超过模式上限');
    for(const k of ['video','audio'])if(items.filter(x=>x.a.kind===k).reduce((n,x)=>n+Number(x.a.duration||0),0)>(m[k+'_total']||10000))fail('素材总时长超过模型上限');
    if(d.video_mode==='reference'&&counts.reference_audio&&!images.length&&!videos.length)missing.push('参考音频还需要搭配图片或视频');
    if(m.voice_binding&&!images.length&&!videos.length)missing.push('R2V还需要参考图片或视频');
    if(['vidu','tx_vidu'].includes(m.adapter)){
      if(videos.length&&(images.length>4||videos.length===2&&videos.some(x=>x.a.duration>5)))fail('带视频时图片最多4张；两段视频各最多5秒');
      if(d.video_mode==='subjects'){
        const groups={};for(const x of items){if(!x.r.subject_name){missing.push('请填写主体分组名称');continue;}(groups[x.r.subject_name]??=[]).push(x);}
        if(Object.keys(groups).length>7)fail('主体分组最多7组');
        for(const group of Object.values(groups))if(group.length>3||new Set(group.map(x=>x.a.kind)).size>1||group[0].a.kind==='video'&&(group.length>1||group[0].a.duration>5))fail('每个主体只能1～3张图或1段不超过5秒的视频');
      }
    }
    return {errors,missing:[...new Set(missing)],counts,items};
  }
  function propose(m,d,ref,resolve,labels={}){
    const a=material(ref,resolve),s=spec(m,d),counts=check(m,d,resolve,labels).counts;
    const choices=Object.keys(s.limits).filter(u=>s.limits[u]>0&&kindOfUsage(u)===a.kind);
    if(board(d)&&s.limits.reference_image>0&&ref.asset_id&&a.kind==='image')choices.unshift('reference_image');
    const preferred=usage({...ref,usage:'auto'},d.video_mode,a.kind);
    choices.sort((a,b)=>Number((s.required[b]||0)>(counts[b]||0))-Number((s.required[a]||0)>(counts[a]||0))||Number(b===preferred)-Number(a===preferred));
    const u=choices.find(u=>board(d)&&a.kind==='image'||(counts[u]||0)<s.limits[u]);
    if(!u)return {error:'当前模式的该类型素材名额已满，或不支持此类型'};
    const next={...ref,usage:u};const before=check(m,d,resolve,labels).errors.map(x=>x.message);
    const after=check(m,{...d,refs:[...d.refs,next]},resolve,labels);
    const error=after.errors.find(x=>x.index===d.refs.length||!before.includes(x.message));
    return error?{error:error.message}:{ref:next};
  }
  function reconcile(m,d,resolve){
    const refs=[];for(const r of d.refs){const next=propose(m,{...d,refs}, {...r,usage:'auto'},resolve);refs.push(next.ref||r);}return refs;
  }
  function parameters(m,d,resolve){
    const s=spec(m,d);let resolutions=[...(s.resolutions||m.resolutions)],durations=[...(s.durations||m.durations)],audio=[...(m.audio_options||['off'])],ratios=[...m.ratios];
    const items=d.refs.map(r=>material(r,resolve)),videos=items.filter(a=>a.kind==='video');
    if(m.adapter==='wan_image'&&items.length)resolutions=resolutions.filter(x=>x!=='4K');
    if(m.adapter==='mini_old'&&d.resolution==='1080P')durations=durations.filter(x=>x===6);
    if(m.adapter==='tx_pixverse'&&m.model.includes('v5.6')&&d.resolution==='1080p')durations=durations.filter(x=>x!==10);
    if(m.adapter==='wan3')durations=durations.filter(x=>x+videos.reduce((n,a)=>n+Number(a.duration||0),0)<=30);
    if(m.adapter==='wan_media'&&m.model.includes('r2v')&&videos.length)durations=durations.filter(x=>x<=10);
    if(m.adapter.includes('kling')){
      if(d.video_mode==='feature'&&m.model.includes('v3'))audio=['off'];
      else if(['edit','feature'].includes(d.video_mode))audio=audio.filter(x=>x!=='native');
      if((m.model.includes('v2-6')||m.model.includes('v2.6'))&&d.audio_mode==='native')resolutions=resolutions.filter(x=>x!=='720p');
    }
    if(m.adapter==='h3'&&d.video_mode==='text')ratios=ratios.filter(x=>x!=='adaptive');
    return {resolution:resolutions,duration:durations,audio_mode:audio,ratio:ratios};
  }
  function requestId(cryptoApi=root.crypto){
    if(typeof cryptoApi?.randomUUID==='function')return cryptoApi.randomUUID();
    if(typeof cryptoApi?.getRandomValues!=='function')throw Error('浏览器不支持安全任务编号，请更新浏览器后重试');
    const bytes=cryptoApi.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
    const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  root.WardrobeInputs={usage,kindOfUsage,check,propose,reconcile,parameters,requestId};
  if(typeof module!=='undefined')module.exports=root.WardrobeInputs;
})(globalThis);
