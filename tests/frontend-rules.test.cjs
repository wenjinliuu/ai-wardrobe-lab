'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const rules=require('../web/input-rules.js');
const models=JSON.parse(readFileSync('config/models.json','utf8'));
const model=id=>models.find(m=>m.id===id);
const draft=(mode='first_frame',refs=[])=>({kind:'video',video_mode:mode,refs,resolution:'480P',duration:5,audio_mode:'native',ratio:'9:16'});
const image=n=>({url:`https://materials.example.com/${n}.png`,vendor_kind:'image',role:'look'});
const resolve=()=>null;
test('HTTP without randomUUID uses secure UUIDv4 and unique values',()=>{
 const crypto={getRandomValues:require('node:crypto').webcrypto.getRandomValues.bind(require('node:crypto').webcrypto)};
 const ids=Array.from({length:500},()=>rules.requestId(crypto));
 assert.equal(new Set(ids).size,500);for(const id of ids)assert.match(id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
 assert.throws(()=>rules.requestId({}),/浏览器/);
});
test('Tencent MiniMax slots: first frame and first/last, no excess',()=>{
 const m=model('tx-minimax-video-h3-max');const d=draft();
 d.refs.push(rules.propose(m,d,image(1),resolve).ref);
 assert.equal(d.refs[0].usage,'first_frame');assert.ok(rules.propose(m,d,image(2),resolve).error);
 d.video_mode='first_last';d.refs.push(rules.propose(m,d,image(2),resolve).ref);
 assert.equal(d.refs[1].usage,'last_frame');assert.ok(rules.propose(m,d,image(3),resolve).error);
 assert.deepEqual(rules.check(m,d,resolve).errors,[]);assert.deepEqual(rules.check(m,d,resolve).missing,[]);
 assert.ok(rules.propose(m,d,d.refs[0],resolve).error);
 d.video_mode='first_frame';d.refs=rules.reconcile(m,d,resolve);
 assert.equal(d.refs.length,2);assert.ok(rules.check(m,d,resolve).errors.length);
 d.refs.pop();assert.deepEqual(rules.check(m,d,resolve).errors,[]);
});
test('motion needs image and video; arbitrary images cannot fill video slot',()=>{
 const m=model('wan-animate'),d=draft('motion');d.refs.push(rules.propose(m,d,image(1),resolve).ref);
 assert.ok(rules.check(m,d,resolve).missing.length);assert.ok(rules.propose(m,d,image(2),resolve).error);
 d.refs.push(rules.propose(m,d,{url:'https://materials.example.com/action.mp4',vendor_kind:'video',duration:5,role:'motion'},resolve).ref);
 assert.equal(d.refs[1].usage,'driving_video');assert.deepEqual(rules.check(m,d,resolve).missing,[]);
});
test('optional collage supports extra local images, rejects external/video',()=>{
 const m=model('seedream'),d={...draft('reference'),kind:'image',reference_board:true};const lookup=id=>({kind:'image',width:512,height:768,size:1000});
 for(let i=0;i<15;i++)d.refs.push(rules.propose(m,d,{asset_id:'local-'+i,role:'upper'},lookup).ref);
 assert.deepEqual(rules.check(m,d,lookup).errors,[]);assert.ok(rules.propose(m,d,image('external'),lookup).error);
 assert.ok(rules.propose(m,d,{url:'https://example.com/v.mp4',vendor_kind:'video',duration:5},lookup).error);
});
test('mixed reference caps and file/link exclusion',()=>{
 const m=models.find(m=>m.max_visual_refs),d=draft('reference');
 for(let i=0;i<m.max_visual_refs;i++)d.refs.push(rules.propose(m,d,image(i),resolve).ref);
 assert.ok(rules.propose(m,d,{url:'https://example.com/v.mp4',vendor_kind:'video',duration:m.video_min,role:'motion'},resolve).error);
 const docs=models.find(m=>Object.values(m.modes).some(s=>s.limits.file&&s.limits.link)),mode=Object.entries(docs.modes).find(([,s])=>s.limits.file&&s.limits.link)[0],e=draft(mode);
 e.refs.push(rules.propose(docs,e,{url:'https://example.com/doc.pdf',vendor_kind:'file',role:'document'},resolve).ref);
 assert.ok(rules.propose(docs,e,{url:'https://example.com/page',vendor_kind:'link',role:'document'},resolve).error);
});
test('parameter combinations reflect model constraints',()=>{
 const mini=models.find(m=>m.adapter==='mini_old'&&m.resolutions.includes('1080P'));
 assert.deepEqual(rules.parameters(mini,{...draft(mini.default_mode),resolution:'1080P'},resolve).duration,[6]);
 const wan=models.find(m=>m.adapter==='wan_image'&&m.resolutions.includes('4K'));
 assert.ok(!rules.parameters(wan,{...draft(wan.default_mode),refs:[image(1)]},resolve).resolution.includes('4K'));
 const pix=models.find(m=>m.adapter==='tx_pixverse'&&m.model.includes('v5.6'));
 assert.ok(!rules.parameters(pix,{...draft(pix.default_mode),resolution:'1080p'},resolve).duration.includes(10));
});
for(const m of models)for(const [mode,s] of Object.entries(m.modes))test(`${m.id}/${mode}: only compatible types and slot counts`,()=>{
 const d={...draft(mode),kind:m.kind==='image'?'image':'video'};
 for(const [u,n] of Object.entries(s.limits)){
  const k=rules.kindOfUsage(u),ref={url:`https://materials.example.com/${m.id}/${u}`,vendor_kind:k,role:k==='image'?'look':k==='audio'?'audio':'motion',duration:m[k+'_min']||1,subject_name:u};
  if(n<=0)continue;
  const proposed=rules.propose(m,d,ref,resolve);
  assert.ok(proposed.ref,JSON.stringify(proposed));assert.equal(rules.kindOfUsage(proposed.ref.usage),k);
 }
 if(!Object.values(s.limits).some(n=>n>0))assert.ok(rules.propose(m,d,image(1),resolve).error);
});
