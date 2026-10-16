import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequestGate} from '../request-gate.mjs';
test('late results cannot overwrite a newer refresh',async()=>{
 const gate=createRequestGate();let visible='initial',resolveOld;
 const first=gate.begin();const old=new Promise(r=>resolveOld=r).then(value=>{if(first())visible=value});
 const next=gate.begin();if(next())visible='fresh';resolveOld('stale');await old;
 assert.equal(visible,'fresh');
});
test('logout or account switch invalidates outstanding responses',()=>{
 const gate=createRequestGate(),old=gate.begin();gate.invalidate();
 assert.equal(old(),false);const current=gate.begin();assert.equal(current(),true);
 gate.invalidate();assert.equal(current(),false);
});

test('changing days invalidates results even before the next day request begins',async()=>{
 const gate=createRequestGate();let shown=null,resolve;
 const old=gate.begin();const response=new Promise(r=>resolve=r).then(v=>{if(old())shown=v});
 gate.invalidate(); // user selects another day before its effect starts
 resolve('previous day');await response;assert.equal(shown,null);
 const next=gate.begin();if(next())shown='selected day';assert.equal(shown,'selected day');
});
