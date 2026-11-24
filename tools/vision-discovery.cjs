// Read-only MCP discovery adapter. No tool execution, no network listener.
'use strict';
const {spawn} = require('node:child_process');
const readline = require('node:readline');
const path = require('node:path');
const fs = require('node:fs');
const allowed = new Set(['initialize','ping','tools/list']);
async function discover(executable, args, cwd, timeoutMs = 8000) {
  const child = spawn(executable, args, {cwd, windowsHide:true, shell:false, stdio:['pipe','pipe','pipe']});
  const pending = new Map();
  let next = 0;
  let closed = false;
  let bytes = 0;
  const fail = () => { for (const p of pending.values()) { clearTimeout(p.timer); p.reject(new Error('Vision discovery unavailable')); } pending.clear(); };
  child.on('error', fail);
  child.on('close', () => {closed=true; fail();});
  child.stderr.resume();
  child.stdin.on('error', fail);
  const lines = readline.createInterface({input:child.stdout});
  child.stdout.on('data', chunk => {bytes += chunk.length; if(bytes > 2*1024*1024){fail(); child.kill();}});
  lines.on('line', line => {
    let r; try {r=JSON.parse(line);} catch {return;}
    if(!r || r.jsonrpc !== '2.0') return;
    const p=pending.get(r.id); if(!p)return;
    pending.delete(r.id); clearTimeout(p.timer);
    if(r.error || !Object.hasOwn(r,'result')) p.reject(new Error('Vision discovery rejected'));
    else p.resolve(r.result);
  });
  function request(method, params={}) {
    if(!allowed.has(method) || closed) return Promise.reject(new Error('Method denied'));
    return new Promise((resolve,reject)=>{
      const id=++next;
      const timer=setTimeout(()=>{pending.delete(id); reject(new Error('Vision discovery timeout'));},timeoutMs);
      pending.set(id,{resolve,reject,timer});
      child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method,params})+'\n');
    });
  }
  try {
    const info=await request('initialize',{protocolVersion:'2025-06-18',capabilities:{},clientInfo:{name:'console-vision-discovery',version:'0.1.0'}});
    if(info.serverInfo?.name !== 'sparks-vision' || info.protocolVersion !== '2025-06-18') throw new Error('Unexpected Vision protocol or identity');
    child.stdin.write(JSON.stringify({jsonrpc:'2.0',method:'notifications/initialized'})+'\n');
    const result=await request('tools/list');
    if(!Array.isArray(result.tools))throw new Error('Invalid capability inventory');
    return {version:String(info.serverInfo.version),tools:[...new Set(result.tools.map(t=>t?.name).filter(n=>typeof n==='string' && /^[a-zA-Z0-9_.-]{1,100}$/.test(n)))].sort(),executionEnabled:false};
  } finally {fail(); lines.close(); child.stdin.end(); const timer=setTimeout(()=>{if(!closed)child.kill();},1500);timer.unref(); }
}
function locate(base) {
  const pointer=JSON.parse(fs.readFileSync(path.join(base,'active-release.json'),'utf8'));
  const releases=fs.realpathSync(path.join(base,'Releases'));
  const root=fs.realpathSync(pointer.path);
  if(path.dirname(root).toLowerCase()!==releases.toLowerCase())throw new Error('Vision release outside managed directory');
  const node=path.join(root,'runtime','node.exe'), entry=path.join(root,'server','index.js');
  for(const f of [node,entry]) {
    const resolved=fs.realpathSync(f);
    if(!resolved.toLowerCase().startsWith(root.toLowerCase()+path.sep)||!fs.statSync(resolved).isFile())throw new Error('Invalid Vision executable or entry');
  }
  return {node,entry,root};
}
module.exports={discover,locate};
