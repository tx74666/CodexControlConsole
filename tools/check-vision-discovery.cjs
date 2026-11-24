const assert=require('node:assert/strict');
const {discover}=require('./vision-discovery.cjs');
const fixture=(name,tools,hang=false)=>"const r=require('node:readline').createInterface({input:process.stdin});r.on('line',l=>{const q=JSON.parse(l);if(!q.id)return;if(q.method==='initialize')console.log(JSON.stringify({jsonrpc:'2.0',id:q.id,result:{protocolVersion:'2025-06-18',serverInfo:{name:"+JSON.stringify(name)+",version:'1.0.0'}}}));else if(q.method==='tools/list'&&!"+hang+")console.log(JSON.stringify({jsonrpc:'2.0',id:q.id,result:{tools:"+JSON.stringify(tools)+"}}));else if(q.method!=='tools/list')process.exit(8);});";
(async()=>{
 const a=await discover(process.execPath,['-e',fixture('sparks-vision',[{name:'system_status'},{name:'system_status'},{name:'bad name'},{name:'pc_engine_status'}])],process.cwd(),2000);
 assert.deepEqual(a,{version:'1.0.0',tools:['pc_engine_status','system_status'],executionEnabled:false});console.log('PASS inventory/dedup/read-only');
 await assert.rejects(discover(process.execPath,['-e',fixture('wrong',[])],process.cwd(),2000),/Unexpected/);console.log('PASS wrong identity');
 await assert.rejects(discover(process.execPath,['-e',fixture('sparks-vision',[],true)],process.cwd(),250),/timeout/);console.log('PASS timeout');
 await assert.rejects(discover(process.execPath,['-e',fixture('sparks-vision',null)],process.cwd(),2000),/Invalid/);console.log('PASS malformed inventory');
})().catch(e=>{console.error(e);process.exitCode=1;});
