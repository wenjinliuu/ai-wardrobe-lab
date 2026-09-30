"""Published list-price estimates; never silently assume unknown charges are zero."""
import math

def estimate(b):
    m=b['model_snapshot'];p=m.get('pricing',{});res=b['resolution'];mode=b['video_mode'];audio=b.get('audio_mode','off');snap=b['asset_snapshot']
    imgs=1 if b['reference_board'] else sum(x['kind']=='image' for x in snap)
    vi=sum(x.get('duration') or 0 for x in snap if x['kind']=='video');ao=sum(x.get('duration') or 0 for x in snap if x['kind']=='audio')
    dur=vi if m['kind']=='motion' and vi or mode=='edit' else ao if mode=='audio_drive' else b['duration']
    if mode=='edit' and m['adapter']=='native_kling_omni':dur=math.floor(dur+.5)
    cost=None;parts=[];confidence='list_price';typ=p.get('type')
    if typ=='image':
        cost=p.get('rates',{}).get(res,p.get('flat'))
        if cost is not None:cost+=max(0,imgs-p.get('free_images',imgs))*p.get('extra_image',0)
        parts.append('单次输出1图；输入图按当前计价规则叠加')
    elif typ=='image_tiers':cost=next((r.get(res) for n,r in p['tiers'] if imgs<=n),None)
    elif typ=='job':cost=p.get('rates',{}).get(res+':'+str(b['duration']),p.get('rates',{}).get(res,p.get('flat')))
    elif typ=='second':
        rates=p.get('rates',{});rates=p.get('mode_rates',{}).get(mode,rates)
        if audio=='native':rates=p.get('audio_rates',rates)
        if vi and p.get('video_rates'):rates=p['video_rates']
        rate=rates.get(res,p.get('flat'))
        if rate is not None:
            cost=rate*dur;parts.append(f'输出 {dur:g}秒 × {rate:g}元/秒')
            if p.get('input_video'):
                billed=min(vi,p['input_cap']) if p.get('input_cap') else vi
                inputrate=p.get('input_rates',rates).get(res,rate);cost+=billed*inputrate
                if billed:parts.append(f'输入视频 {billed:g}秒 × {inputrate:g}元/秒')
            extra=max(0,imgs-p.get('free_images',imgs))*p.get('extra_image',0);cost+=extra
            if extra:parts.append(f'额外参考图 {extra:g}元')
    elif typ=='vidu_q2':
        v=p['version'];idx=['540p','720p','1080p'].index(res);d=dur;ref=mode in ('reference','subjects')
        if v=='q2-pro' and ref:first=[.625,.9375,2.65625][idx];sub=[.15625,.15625,.3125][idx];cost=first+(d-1)*sub
        elif v=='q2' and ref:cost=[.46875,.78125,2.34375][idx]+(d-1)*[.15625,.15625,.3125][idx]
        elif v=='q2':cost=[.3125,.46875,.625][idx]+(d-1)*[.0625,.15625,.3125][idx]
        elif v=='q2-pro':
            cost=(.25 if d==1 else .3125+(d-2)*.15625) if idx==0 else [.0,.46875,1.71875][idx]+(d-1)*[.0,.3125,.46875][idx]
        else:cost=(.25 if d==1 else .3125+(d-2)*.3125) if idx==1 else [.1875,.0,1.09375][idx]+(d-1)*[.0625,.0,.3125][idx]
        if audio=='native':cost+=.46875
        parts.append('Q2按首秒/后续秒分段计费；声音额外0.46875元/次')
    elif typ=='token':
        # Input video minimum tokens and adaptive raster dimensions make a fixed quote misleading.
        confidence='lower_bound' if vi else 'approximate'
        short={'480p':480,'720p':720,'1080p':1080}[res]
        w,h=map(int,('16:9' if b['ratio']=='adaptive' else b['ratio']).split(':'))
        width=round(short*max(w/h,1));height=round(short*max(h/w,1));tokens=(vi+dur)*width*height*24/1024
        rate=(p['video_rates_million'] if vi else p['rates_million'])[res];cost=tokens/1e6*rate
        parts.append(f'近似Token=(输入+输出秒数)×输出像素×24/1024；{rate}元/百万Token')
        if vi:parts.append('含输入视频有最低Token计量，本数字只是下界，不是完整报价')
    if cost is not None:cost=round(cost,5)
    return dict(estimated_cny=0 if b['mode']=='mock' else cost,reference_cny=cost,confidence=confidence,price_date=m.get('price_date'),source='官方刊例参考' if cost is not None else '价格待账户后台核对',price_source=m.get('price_source'),breakdown=parts,discount_note=m.get('discount_note',''),note='模拟不调用模型，费用为0。真实费用以供应商账单为准；预算预占只限制本站新增任务，不是供应商费用硬上限。'+(' Token估算无法作为费用上限。' if typ=='token' else ''))
