export function createClient({baseUrl, token, fetchImpl = fetch}) {
  const base = new URL(baseUrl);
  if (base.protocol !== 'https:' || base.username || base.password || base.search || base.hash || base.pathname !== '/') throw Error('LOVEDAYS_URL 必须是 HTTPS 网站根地址');
  if (!token || token.length < 32) throw Error('缺少有效的 WHALE_API_TOKEN');
  return async function request(path, body) {
    if (!/^\/api\/whale\/agent\//.test(path)) throw Error('接口范围无效');
    const url = new URL(path,base);
    if(url.origin!==base.origin || !url.pathname.startsWith('/api/whale/agent/')) throw Error('接口范围无效');
    const res = await fetchImpl(url, {
      method:body === undefined ? 'GET' : 'POST', redirect:'error',
      headers:{Authorization:'Bearer '+token,'X-Blue-Request':'1','Content-Type':'application/json'},
      ...(body === undefined ? {} : {body:JSON.stringify(body)}), signal:AbortSignal.timeout(20000),
    });
    if (!res.ok) throw Error('Love Days 接口返回 HTTP '+res.status);
    return res.json();
  };
}
