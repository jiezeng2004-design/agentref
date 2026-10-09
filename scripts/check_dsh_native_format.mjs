// Generate a synthetic compressed log using the installed DSH Session API.
// No DSH configuration, services, credentials or private history are opened.
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { zstdCompressSync } from 'node:zlib';
import { createRequire } from 'node:module';

const [modulePath, outputRoot] = process.argv.slice(2);
if (!modulePath || !outputRoot) throw new Error('Usage: node check_dsh_native_format.mjs <dsh-session/lib/index.js> <output root>');
const { Session, SessionId, packChunkRuns } = await import(pathToFileURL(resolve(modulePath)).href);
const session = Session.create(SessionId('session-native-format'));
session.append('user/message', {id:'u1', role:'user', source:{kind:'user'}, content:[{type:'text',text:'Verify the DSH native format'}]}, {surfaceOp:'append'});
if (session.header.version === 4) {
    const require = createRequire(resolve(modulePath));
    const { Context } = await import(pathToFileURL(require.resolve('@deepseek-ai/cordis')).href);
    const { default: Persistence } = await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-session-persistence-jsonl')).href);
    session.append('turn/start', {turn:1});
    session.append('step/start', {turn:1,step:1});
    const answer = 'Native API synthetic response';
    session.append('assistant/message', {turn:1,step:1,message:{id:'a1',role:'assistant',source:{kind:'model',provider:'synthetic',model:'synthetic'},content:[{type:'text',text:answer}]},stream:[{type:'text-chunks',time0:Date.now(),index:0,dt:[],texts:[answer]}]}, {surfaceOp:'append'});
    session.append('step/end', {turn:1,step:1});
    session.append('turn/end', {turn:1,reason:{kind:'completed'}});
    const ctx = new Context();
    try {
        await ctx.plugin(Persistence, {root:join(resolve(outputRoot),'sessions'),compression:'zstd'});
        const handle = await ctx.sessionPersistence.create(session.header);
        await handle.append(session.snapshotEvents());
        await handle.flush();
        const read = await ctx.sessionPersistence.open(session.id,'read');
        if ((await read.read()).events.length !== session.snapshotEvents().length) throw new Error('Official read-back mismatch');
        await read.close();
        await handle.close();
    } finally { await ctx.fiber.dispose(); }
    console.log(JSON.stringify({nativeApi:'DSH SessionHandle JSONL writer',version:4,eventCount:session.snapshotEvents().length,synthetic:true,compressed:true}));
} else {
if (session.header.version !== 0 || typeof packChunkRuns !== 'function') throw new Error('Unsupported DSH native fixture version');
session.append('assistant/message', {turn:0, step:0, message:{id:'a1',role:'assistant',source:{kind:'model',provider:'synthetic',model:'synthetic'},content:[{type:'text',text:'Native API synthetic response'}]}}, {surfaceOp:'append'});
session.append('tool/call', {turn:0,step:0,callId:'tool1',name:'shell',arguments:'{"command":"python -m unittest"}'});
session.append('tool/result', {turn:0,step:0,message:{id:'t1',role:'user',source:{kind:'tool',tool:'shell'},content:[{type:'tool-result',toolCallId:'tool1',content:[{type:'text',text:'{"exit_code":0}'}]}]}}, {surfaceOp:'append'});
session.append('turn/end', {turn:0,reason:{kind:'completed'}});
const { isSeeded, ...header } = session.header;
const records = [{type:'session',...header,delegationDepth:0}, ...packChunkRuns(session.snapshotEvents())];
const folder = join(resolve(outputRoot),'sessions','synthetic-project','session-native-format');
await mkdir(folder,{recursive:true});
await writeFile(join(folder,'session.jsonl.zstd'), zstdCompressSync(Buffer.from(records.map(x=>JSON.stringify(x)+'\n').join(''))));
console.log(JSON.stringify({nativeApi:'DSH Session',eventCount:session.snapshotEvents().length,synthetic:true,compressed:true}));
}
