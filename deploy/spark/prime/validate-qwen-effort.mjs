// Run with Prime's bundled Node in its runtime image; no external API calls.
import http from 'node:http';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const {streamSimpleOpenAICompletions} = await import(process.env.PRIME_AI_PROVIDER || '/usr/local/lib/node_modules/prime-agent/node_modules/@earendil-works/pi-ai/dist/providers/openai-completions.js');
const provider = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).providers['spark-qwen'];
let captured;
const server = http.createServer(async (req, res) => {
  let body=''; for await (const chunk of req) body+=chunk;
  captured=JSON.parse(body);
  res.writeHead(200, {'Content-Type':'text/event-stream'});
  res.end('data: '+JSON.stringify({id:'fixture',choices:[{index:0,delta:{role:'assistant',content:'OK'},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const model={...provider.models[0],provider:'spark-qwen',api:provider.api,compat:provider.compat,
  baseUrl:`http://127.0.0.1:${server.address().port}/v1`,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}};
try {
  for (const [reasoning, expected] of [['low','low'],['high','xhigh'],['max','xhigh'],['minimal','low'],['off','none']]) {
    captured=null;
    const stream=streamSimpleOpenAICompletions(model,{messages:[{role:'user',content:'Synthetic effort test',timestamp:Date.now()}]}, {apiKey:'fixture',reasoning,maxTokens:16});
    const result=await stream.result();
    assert.notEqual(result.stopReason,'error',result.errorMessage);
    assert.equal(captured.reasoning_effort,expected);
    console.log(`PASS ${reasoning||'off'} -> reasoning_effort=${expected}`);
  }
} finally {server.close();}
