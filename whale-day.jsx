import React, {useState} from 'react';
import {api} from './api.mjs';

export function WhaleDay({day, entries, refresh}) {
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  if (!entries.length) return null;
  const done = entries.filter(e => e.whale_state === 'done').length;
  const failed = entries.filter(e => e.whale_state === 'failed').length;
  const waiting = entries.filter(e => ['queued','reading'].includes(e.whale_state)).length;
  const canInvite = done + waiting < entries.length;

  async function invite() {
    setBusy(true);
    setError('');
    try {
      await api('/api/whale/read-day/'+day, {method:'POST'});
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return <section aria-label="小铃读日记">
    <button type="button" className="emoji-trigger" disabled={busy || !canInvite} onClick={invite}>
      {busy ? '正在邀请…' : failed ? '让小铃重试' : done === entries.length ? '小铃已回复' :
        waiting && !canInvite ? '等小铃读完…' : '🎀 让小铃看看这一天'}
    </button>
    <small role="status"> {done}/{entries.length} 篇已回复{failed > 0 && ' · 有帖子读取失败，可重试'}</small>
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}
