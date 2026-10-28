import {readFile} from 'node:fs/promises';
import {createClient} from './client.mjs';
try {
  const request = createClient({baseUrl:process.env.LOVEDAYS_URL,token:process.env.WHALE_API_TOKEN});
  const [command, ...args] = process.argv.slice(2);
  let result;
  if (command === 'entries') {
    const query = new URLSearchParams();
    for(let i=0;i<args.length;i+=2) {
      const k = {'--day':'day','--before':'before','--limit':'limit'}[args[i]];
      if (!k || !args[i+1]) throw Error('用法：entries [--day YYYY-MM-DD] [--before ID] [--limit 10]');
      query.set(k,args[i+1]);
    }
    result = await request('/api/whale/agent/entries?'+query);
  } else if (['inbox','history'].includes(command) && !args.length) result = await request('/api/whale/agent/'+command);
  else if (command === 'reply' && /^\d+$/.test(args[0]||'') && args[1] === '--file' && args.length === 3) {
    const body = await readFile(args[2],'utf8');
    if (!body.trim() || body.length > 4000) throw Error('回复须为 1–4000 字');
    result = await request('/api/whale/agent/reply/'+args[0],{body});
  } else throw Error('用法：entries / inbox / history / reply ID --file PATH');
  console.log(JSON.stringify(result,null,2));
} catch(e) { console.error(e.message); process.exitCode = 1; }
