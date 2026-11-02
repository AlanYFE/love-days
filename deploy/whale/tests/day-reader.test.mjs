import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {makeDayReader} from '../day-reader.mjs';

test('submit real image blocks to DSH and fail the whole post if a preview is missing',async()=>{
  const cwd = await fs.mkdtemp(path.join(os.tmpdir(),'day-reader-'));
  try {
    const personaPath = path.join(cwd,'persona.md');
    await fs.writeFile(personaPath,'镜音铃');
    const prompts=[], failures=[];
    const job={ticket:'a'.repeat(32),day:'2026-11-02',author:'测试',body:'正文',comments:[{body:'留言'}],images:['a','b']};
    let missing=false;
    const tick=makeDayReader({cwd,personaPath,cliPath:'/tmp/cli.mjs',log:()=>{},
      request:async url=>{
        if (url.endsWith('/claim')) return {job};
        if (url.endsWith('/fail')) {failures.push(url);return {};}
        if (missing && url.endsWith('/b')) throw Error('missing');
        return {jpeg:Buffer.from(url).toString('base64')};
      },
      controller:{create:async()=>{},prompt:async (r,signal)=>{assert.ok(signal instanceof AbortSignal);prompts.push(r);}},
    });
    await Promise.all([tick(),tick()]);
    assert.equal(prompts.length,1);
    assert.deepEqual(prompts[0].content.map(p=>p.type),['text','image','image']);
    assert.equal(prompts[0].content[1].mediaType,'image/jpeg');
    assert.match(prompts[0].content[0].text,/镜音铃/);
    assert.match(prompts[0].content[0].text,/留言/);
    missing=true;await tick();
    assert.equal(prompts.length,1);
    assert.equal(failures.length,1);
  } finally {await fs.rm(cwd,{recursive:true,force:true});}
});
