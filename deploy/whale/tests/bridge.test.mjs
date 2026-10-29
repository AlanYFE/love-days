import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createClient} from '../client.mjs';
import {createPoller} from '../plugin.mjs';

test('client restricts token to HTTPS agent routes and rejects redirects',async()=>{
  for(const baseUrl of ['http://test.local','https://x.local/path','https://u:p@x.local/'])assert.throws(()=>createClient({baseUrl,token:'x'.repeat(40)}));
  let seen;
  const client=createClient({baseUrl:'https://love.example',token:'x'.repeat(40),fetchImpl:async(url,opts)=>{seen={url,opts};return {ok:true,json:async()=>({ok:true})};}});
  await client('/api/whale/agent/inbox');
  assert.equal(seen.url.origin,'https://love.example');assert.equal(seen.opts.redirect,'error');
  assert.equal(seen.opts.headers.Authorization,'Bearer '+'x'.repeat(40));
  await assert.rejects(client('https://evil.local/'));await assert.rejects(client('/api/export'));
});

test('polling is single flight, persists capped retries, and recovers after restart',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'whale-'));
  try{
    let clock=0,calls=0,sessionId;
    const settings={statePath:path.join(dir,'state.json'),cwd:dir,now:()=>clock,request:async()=>({messages:[{id:1,body:'hi',author:'Alan'}]}),controller:{create:async r=>{sessionId=r.sessionId;},prompt:async r=>{calls++;assert.equal(r.sessionId,sessionId);assert.ok(r.content[0].text.includes('reply 1 --file'));}}};
    const poller=createPoller(settings);
    await Promise.all([poller.tick(),poller.tick()]);assert.equal(calls,1);
    await poller.tick();assert.equal(calls,1);
    clock=16*60000;await createPoller(settings).tick();assert.equal(calls,2);
    clock=32*60000;await createPoller(settings).tick();assert.equal(calls,2);
    clock=86400000;await createPoller(settings).tick();assert.equal(calls,3);
    poller.stop();clock+=86400000;await poller.tick();assert.equal(calls,3);
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
});

test('uncertain prompt failure does not immediately repeat a paid turn',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'whale-fail-'));let attempts=0;
  try{
    const poller=createPoller({statePath:path.join(dir,'state.json'),cwd:dir,now:()=>0,request:async()=>({messages:[{id:2}]}),controller:{create:async()=>{},prompt:async()=>{attempts++;throw Error('timeout');}}});
    await poller.tick();await poller.tick();assert.equal(attempts,1);
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
});

test('native deployment quotes paths and gives each message a distinct reply file',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),"xiaoling's room "));
  try {
    const personaPath=path.join(dir,'persona.md');
    fs.writeFileSync(personaPath,'你叫小铃。');
    const prompts=[];
    let id=51;
    const poller=createPoller({
      statePath:path.join(dir,'state.json'),cwd:dir,personaPath,
      cliPath:path.join(dir,'cli.mjs'),nodePath:'/custom node/bin/node',
      request:async()=>({messages:[{id:id++,body:'hello',author:'Joey'}]}),
      controller:{create:async()=>{},prompt:async r=>prompts.push(r.content[0].text)},
    });
    await poller.tick();
    fs.writeFileSync(personaPath,'你叫小铃，更新后的人设。');
    await poller.tick();
    assert.ok(prompts[0].startsWith('你叫小铃。'));
    assert.ok(prompts[1].startsWith('你叫小铃，更新后的人设。'));
    assert.ok(prompts[0].includes("'/custom node/bin/node'"));
    assert.ok(prompts[0].includes("xiaoling'\\''s room"));
    assert.ok(prompts[0].includes('reply-51.txt'));
    assert.ok(prompts[1].includes('reply-52.txt'));
    assert.ok(!prompts[0].includes('/opt/lovedays'));
    assert.ok(!prompts[0].includes('/opt/dsh-bili-whale'));
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
