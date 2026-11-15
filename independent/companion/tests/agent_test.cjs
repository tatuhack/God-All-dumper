const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/../agent.js', 'utf8');
let passed=0;
function fixture(overrides={}) {
  const memory = Buffer.alloc(0x4000);
  memory.writeUInt32LE(0x464c457f,0); memory[4]=2; memory[5]=1;
  memory.writeUInt16LE(183,18); memory.writeBigUInt64LE(64n,32);
  memory.writeUInt16LE(56,54); memory.writeUInt16LE(2,56);
  memory.writeUInt32LE(1,64); memory.writeBigUInt64LE(0n,72); memory.writeBigUInt64LE(0n,80); memory.writeBigUInt64LE(0x2000n,104);
  memory.writeUInt32LE(1,120); memory.writeUInt32LE(5,124); memory.writeBigUInt64LE(0x2000n,128); memory.writeBigUInt64LE(0x2000n,136); memory.writeBigUInt64LE(0x2000n,160);
  class P {
    constructor(n){this.n=BigInt(n instanceof P ? n.n:n)}
    add(n){return new P(this.n+BigInt(n instanceof P ? n.n:n))}
    and(n){return new P(this.n&BigInt(n))} or(n){return new P(this.n|BigInt(n))}
    isNull(){return this.n===0n} compare(p){return this.n<p.n?-1:this.n>p.n?1:0}
    toString(){return '0x'+this.n.toString(16)} toUInt32(){return Number(this.n&0xffffffffn)}
    readU8(){return memory.readUInt8(Number(this.n-0x100000n))}
    readU16(){return memory.readUInt16LE(Number(this.n-0x100000n))}
    readU32(){return memory.readUInt32LE(Number(this.n-0x100000n))}
    readU64(){const n=memory.readBigUInt64LE(Number(this.n-0x100000n)); return {compare(v){return n<v?-1:n>v?1:0},toNumber(){return Number(n)}}}
  }
  let callbacks, detached=0, timeout, now=0, executable=true;
  const config = {label:'Example::Add',method_id:1,module:'/test/lib.so',rva:'0x2000',elf_min_vaddr:'0x0',
    thumb:false,arch:'arm64',calling:'instance',parameters:['i32'],result:'i32',shared_records:1,
    ttl_seconds:60,max_calls:1000,edits:{args:{},return:null},...overrides};
  const events=[];
  const context={PXO_CONFIG:config,ptr:n=>new P(n),uint64:BigInt,Date:{now:()=>now},
    Process:{platform:'linux',arch:config.arch,pointerSize:8,pageSize:4096,
      enumerateModules:()=>[{path:'/test/lib.so',name:'lib.so',base:new P(0x100000),size:0x4000}],
      findRangeByAddress:()=>({protection:executable?'r-x':'r--'})},
    Interceptor:{attach(target,c){callbacks=c; return {detach(){detached++}}}},
    Frida:{version:'mock'},send:e=>events.push(e),rpc:{},
    setTimeout:f=>{timeout=f;return 1},clearTimeout:()=>{},setInterval:()=>2,clearInterval:()=>{}};
  vm.runInNewContext(source,context);
  function enter(values=[1234,10]){const call={threadId:7};const args=values.map(n=>new P(n)); callbacks.onEnter.call(call,args);return {call,args}}
  function leave(call,value=20){let n=new P(value);n.replace=v=>{n.n=v.n};if(callbacks.onLeave) callbacks.onLeave.call(call,n);return n.toUInt32()}
  return {api:context.rpc.exports,enter,leave,events,config,memory,context,
    detached:()=>detached,expire:()=>{now=61000;timeout()},setNow:n=>now=n,noExec:()=>executable=false};
}
function test(name,run){run();passed++;console.log('PASS '+name)}
test('load does not attach; confirmations required',()=>{const f=fixture();assert.equal(f.api.status().active,false);assert.throws(()=>f.api.start());assert.throws(()=>f.api.arm('ARM'))});
test('ASLR rebased from live module, observer only',()=>{const f=fixture();f.api.start('SAME BUILD');assert.equal(f.api.status().resolved.address,'0x102000');const {call,args}=f.enter();assert.equal(args[1].toUInt32(),10);assert.equal(f.leave(call),20)});
test('instance argument shift, signed decode, return replacement',()=>{const f=fixture();f.api.start('SAME BUILD');f.api.setarg(0,-5);f.api.setreturn(99);f.api.arm('ARM');const {call,args}=f.enter();assert.equal(args[0].toUInt32(),1234);assert.equal(args[1].toUInt32(),0xfffffffb);assert.equal(f.leave(call),99);f.api.stop();assert.equal(f.events.at(-2).events[0].arguments_after[0],-5)});
test('staging always disarms',()=>{const f=fixture();f.api.start('SAME BUILD');f.api.setarg(0,5);f.api.arm('ARM');f.api.setreturn(8);assert.equal(f.api.status().armed,false)});
test('disarm cancels in-flight return edit',()=>{const f=fixture();f.api.start('SAME BUILD');f.api.setreturn(99);f.api.arm('ARM');const {call}=f.enter();f.api.disarm();assert.equal(f.leave(call),20)});
test('rearm does not mutate prior generation',()=>{const f=fixture();f.api.start('SAME BUILD');f.api.setreturn(99);f.api.arm('ARM');const {call}=f.enter();f.api.disarm();f.api.arm('ARM');assert.equal(f.leave(call),20)});
test('TTL detaches and disarms',()=>{const f=fixture();f.api.start('SAME BUILD');f.api.setreturn(9);f.api.arm('ARM');f.expire();assert.equal(f.api.status().active,false);assert.equal(f.detached(),1)});
test('call limit detaches',()=>{const f=fixture({max_calls:1});f.api.start('SAME BUILD');const {call}=f.enter();f.leave(call);assert.equal(f.api.status().count,1);assert.equal(f.api.status().active,false)});
test('bounded log queue and dropped count',()=>{const f=fixture();f.api.start('SAME BUILD');for(let i=0;i<30;i++){const {call}=f.enter();f.leave(call)}assert.equal(f.api.status().count,30);assert.equal(f.api.status().dropped_logs,20)});
test('unsupported signatures rejected in agent',()=>{const f=fixture({parameters:['float']});assert.throws(()=>f.api.start('SAME BUILD'))});
test('shared implementation rejected for values',()=>{const f=fixture({shared_records:2});assert.throws(()=>f.api.start('SAME BUILD'))});
test('non-executable target rejected',()=>{const f=fixture();f.noExec();assert.throws(()=>f.api.start('SAME BUILD'))});
test('ELF evidence mismatch rejected',()=>{const f=fixture({elf_min_vaddr:'0x1000'});assert.throws(()=>f.api.start('SAME BUILD'))});
test('wrong ABI rejected',()=>{const f=fixture();f.context.Process.arch='x64';assert.throws(()=>f.api.start('SAME BUILD'))});
test('wrong same-build string rejected',()=>{const f=fixture();assert.throws(()=>f.api.start('yes'))});
test('value range checked again in agent',()=>{const f=fixture();assert.throws(()=>f.api.setarg(0,2147483648));assert.throws(()=>f.api.setreturn(1.5))});
test('static argument is first register',()=>{const f=fixture({calling:'static'});f.api.start('SAME BUILD');f.api.setarg(0,5);f.api.arm('ARM');const {call,args}=f.enter();assert.equal(args[0].toUInt32(),5);f.leave(call)});
test('hits-only does not decode or mutate registers',()=>{const f=fixture({calling:'hits',parameters:[],result:'unknown'});f.api.start('SAME BUILD');assert.throws(()=>f.api.setarg(0,5));const {call,args}=f.enter();f.leave(call);f.api.stop();assert.equal('arguments_before' in f.events.at(-2).events[0],false)});
test('staged edits still off after restart',()=>{const f=fixture();f.api.start('SAME BUILD');f.api.setreturn(99);f.api.arm('ARM');f.api.stop();f.api.start('SAME BUILD');const {call}=f.enter();assert.equal(f.leave(call),20)});
test('old callbacks cannot corrupt restarted session',()=>{const f=fixture();f.api.start('SAME BUILD');const {call}=f.enter();f.api.stop();f.api.start('SAME BUILD');f.leave(call);assert.equal(f.api.status().count,0);assert.equal(f.api.status().changed_calls,0);assert.equal(f.api.status().active,true)});
test('hits-only logs a nonreturning call',()=>{const f=fixture({calling:'hits',parameters:[],result:'unknown'});f.api.start('SAME BUILD');f.enter();f.api.stop();assert.equal(f.events.at(-2).events[0].phase,'enter')});
console.log(`${passed} agent tests passed`);
