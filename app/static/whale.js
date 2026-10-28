const $ = id => document.getElementById(id);
let active = true, busy = false, ready = false, pending = null, sending = false, previous = '';
async function request(path, options = {}) {
  const r = await fetch(path, {...options, headers:{'X-Blue-Request':'1','Content-Type':'application/json'}});
  const data = await r.json();
  if (!r.ok) {
    if (r.status === 401) { active = false; ready = false; $('send').disabled = true; }
    throw Error(typeof data.detail === 'string' ? data.detail : '请求失败，请重试');
  }
  return data;
}
async function refresh() {
  if (!active || busy || document.hidden) return;
  busy = true;
  try {
    const data = await request('/api/whale/messages');
    ready = data.enabled;
    const fingerprint = JSON.stringify(data.messages);
    if (fingerprint !== previous) {
      const nodes = data.messages.map(m => {
        const el = document.createElement('article');
        el.className = m.user_id ? 'human' : 'whale';
        const meta = document.createElement('small');
        meta.textContent = m.author + ' · ' + new Date(m.created * 1000).toLocaleString('zh-CN');
        const body = document.createElement('p'); body.textContent = m.body;
        el.append(meta,body); return el;
      });
      $('messages').replaceChildren(...nodes); previous = fingerprint;
    }
    $('status').textContent = data.enabled ? '消息发送后会排队，小鲸鱼需要一点时间回复。显示最近 100 条。' : '小鲸鱼尚未接入，暂时不能发送消息。';
  } catch(e) { $('status').textContent = e.message; }
  finally { busy = false; $('send').disabled = !ready || sending; }
}
$('chat').addEventListener('submit', async e => {
  e.preventDefault(); if (!ready || $('send').disabled) return;
  const body = $('body').value.trim(); if (!body) return;
  if (!pending || pending.body !== body) pending = {client_id:crypto.randomUUID(),body};
  sending = true; $('send').disabled = true;
  try { await request('/api/whale/messages',{method:'POST',body:JSON.stringify(pending)}); pending = null; $('body').value = ''; await refresh(); }
  catch(e) { $('status').textContent = e.message; }
  finally { sending = false; $('send').disabled = !ready; }
});
document.addEventListener('visibilitychange',refresh);
window.addEventListener('focus',refresh);
setInterval(refresh,5000);
refresh();
