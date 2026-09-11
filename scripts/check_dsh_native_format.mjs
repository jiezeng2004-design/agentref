// Generate a synthetic compressed log using the installed DSH Session API.
// No DSH configuration, services, credentials or private history are opened.
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { zstdCompressSync } from 'node:zlib';

const [modulePath, outputRoot] = process.argv.slice(2);
if (!modulePath || !outputRoot) throw new Error('Usage: node check_dsh_native_format.mjs <dsh-session/lib/index.js> <output root>');
const { Session, SessionId, packChunkRuns } = await import(pathToFileURL(resolve(modulePath)).href);
const session = Session.create(SessionId('session-native-format'));
session.append('user/message', {id:'u1', role:'user', source:{kind:'user'}, content:[{type:'text',text:'Verify the DSH native format'}]}, {surfaceOp:'append'});
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
