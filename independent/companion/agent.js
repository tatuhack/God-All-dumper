// PXOJ Phantom agent. No Java bridge, eval, NativeFunction replacement, or persistent patch.
// Generated PXO_CONFIG is data only. Public controls are also exported over Frida RPC.
const pxo = (() => {
    const c = PXO_CONFIG;
    const ranges = {bool:[0,1], i8:[-128,127], u8:[0,255], i16:[-32768,32767],
        u16:[0,65535], i32:[-2147483648,2147483647], u32:[0,4294967295]};
    let active = false, armed = false, listener = null, timer = null, pump = null;
    let count = 0, changedCalls = 0, dropped = 0, queue = [], generation = 0;
    let sessionGeneration = 0;
    let resolved = null, edits = JSON.parse(JSON.stringify(c.edits)), deadline = 0;
    function emit(event) { send({product: 'PXOJ Phantom', ...event}); }
    function flush() {
        if (queue.length) { const events = queue; queue = []; emit({event:'calls', events}); }
    }
    function status() {
        return {active, armed, method:c.label, method_id:c.method_id, resolved,
            count, changed_calls:changedCalls, dropped_logs:dropped, deadline,
            edits:JSON.parse(JSON.stringify(edits)), shared_records:c.shared_records};
    }
    function stop(reason = 'user') {
        armed = false; active = false; generation++; sessionGeneration++;
        if (listener !== null) { listener.detach(); listener = null; }
        if (timer !== null) { clearTimeout(timer); timer = null; }
        if (pump !== null) { clearInterval(pump); pump = null; }
        flush(); emit({event:'stopped', reason, ...status()});
        return status();
    }
    function checkValue(kind, value) {
        if (!(kind in ranges) || !Number.isInteger(value) || value < ranges[kind][0] || value > ranges[kind][1])
            throw new Error('Unsupported type or value out of range');
        return value;
    }
    function decode(pointer, kind) {
        const n = pointer.toUInt32();
        switch (kind) {
            case 'bool': return (n & 255) !== 0;
            case 'i8': return (n << 24) >> 24;
            case 'u8': return n & 255;
            case 'i16': return (n << 16) >> 16;
            case 'u16': return n & 65535;
            case 'i32': return n | 0;
            case 'u32': return n;
            default: throw new Error('Unsupported decode');
        }
    }
    function bits(value) { return ptr('0x' + (value >>> 0).toString(16)); }
    function setarg(index, value) {
        if (c.calling === 'hits' || !Number.isInteger(index) || index < 0 || index >= c.parameters.length)
            throw new Error('Unsupported argument');
        checkValue(c.parameters[index], value);
        disarm(); edits.args[String(index)] = value; return status();
    }
    function setreturn(value) {
        checkValue(c.result, value); disarm(); edits.return = value; return status();
    }
    function disarm() { armed = false; generation++; return status(); }
    function clear() { disarm(); edits = {args:{}, return:null}; return status(); }
    function arm(confirmation) {
        if (confirmation !== 'ARM' || !active || Date.now() >= deadline || c.calling === 'hits')
            throw new Error('Start a supported typed session and confirm ARM first');
        if (!Object.keys(edits.args).length && edits.return === null) throw new Error('No staged edits');
        generation++; armed = true; emit({event:'armed', ...status()}); return status();
    }
    function readElf(module) {
        const b = module.base;
        if (b.readU32() !== 0x464c457f || b.add(5).readU8() !== 1) throw new Error('Readable little-endian ELF header required');
        const cls = b.add(4).readU8();
        if (cls !== (Process.pointerSize === 8 ? 2 : 1)) throw new Error('ELF class differs from live process');
        const machines = {arm:40, arm64:183, ia32:3, x64:62};
        if (b.add(18).readU16() !== machines[c.arch]) throw new Error('ELF machine mismatch');
        function small64(at) {
            const value = at.readU64();
            if (value.compare(uint64('0x7fffffff')) > 0) throw new Error('Large ELF layout is unsupported');
            return value.toNumber();
        }
        const phoff = cls === 2 ? small64(b.add(32)) : b.add(28).readU32();
        const entsize = b.add(cls === 2 ? 54 : 42).readU16();
        const number = b.add(cls === 2 ? 56 : 44).readU16();
        if (entsize !== (cls === 2 ? 56 : 32) || !number || number > 1024 || phoff > 1048576 || phoff + number * entsize > module.size)
            throw new Error('ELF program headers unsupported');
        let min = Infinity, zeroLoad = false;
        const exec = [];
        for (let i = 0; i < number; i++) {
            const p = b.add(phoff + i * entsize);
            if (p.readU32() !== 1) continue;
            const flags = p.add(cls === 2 ? 4 : 24).readU32();
            const offset = cls === 2 ? small64(p.add(8)) : p.add(4).readU32();
            const vaddr = cls === 2 ? small64(p.add(16)) : p.add(8).readU32();
            const memsz = cls === 2 ? small64(p.add(40)) : p.add(20).readU32();
            if (vaddr < min) { min = vaddr; zeroLoad = offset === 0; }
            if (flags & 1) exec.push([vaddr, memsz]);
        }
        // Strict subset: refuse unusual unaligned/nonzero-offset first PT_LOAD.
        if (!Number.isFinite(min) || !zeroLoad || min % Process.pageSize !== 0)
            throw new Error('Unsupported ELF image-base convention');
        if (min !== parseInt(c.elf_min_vaddr, 16)) throw new Error('ELF minimum PT_LOAD differs from dump');
        const rva = parseInt(c.rva, 16), vaddr = min + rva;
        if (!exec.some(([start, size]) => vaddr >= start && vaddr - start < size))
            throw new Error('RVA is outside executable PT_LOAD');
        return b.add(c.rva);
    }
    function resolve() {
        if (Process.platform !== 'linux' || Process.arch !== c.arch) throw new Error('Selected ABI differs from live Linux/Android process');
        if (!Number.isInteger(c.ttl_seconds) || c.ttl_seconds < 1 || c.ttl_seconds > 3600 || !Number.isInteger(c.max_calls) || c.max_calls < 1 || c.max_calls > 1000000)
            throw new Error('Invalid session limits');
        if (!['hits','static','instance'].includes(c.calling)) throw new Error('Invalid calling layout');
        if (c.calling !== 'hits' && (!['arm64','x64'].includes(c.arch) || c.shared_records > 1 ||
            !c.parameters.every(t => t in ranges) || (c.result !== 'void' && !(c.result in ranges)) ||
            c.parameters.length + (c.calling === 'instance' ? 1 : 0) > (c.arch === 'arm64' ? 8 : 6)))
            throw new Error('Unsupported typed ABI');
        if (!/^0x[0-9a-fA-F]{1,8}$/.test(c.rva) || parseInt(c.rva,16) > 0x7fffffff) throw new Error('Invalid RVA');
        for (const [index, value] of Object.entries(edits.args)) {
            if (!/^\d+$/.test(index) || Number(index) >= c.parameters.length) throw new Error('Invalid staged argument');
            checkValue(c.parameters[Number(index)], value);
        }
        if (edits.return !== null) checkValue(c.result, edits.return);
        const modules = Process.enumerateModules();
        const exact = modules.filter(m => m.path === c.module);
        const name = c.module.split('/').pop();
        const candidates = exact.length ? exact : modules.filter(m => m.name === name);
        if (candidates.length !== 1) throw new Error('Module missing or ambiguous; launch target first and use its matching dump');
        const module = candidates[0], address = readElf(module);
        if (address.compare(module.base) < 0 || address.compare(module.base.add(module.size)) >= 0) throw new Error('RVA outside module');
        const range = Process.findRangeByAddress(address);
        if (!range || !range.protection.includes('x')) throw new Error('Target is not currently executable');
        if (c.thumb && c.arch !== 'arm') throw new Error('Thumb requires ARM32');
        if ((c.arch === 'arm64' || (c.arch === 'arm' && !c.thumb)) && !address.and(3).isNull())
            throw new Error('Unaligned instruction address');
        if (c.arch === 'arm' && c.thumb && !address.and(1).isNull()) throw new Error('Unaligned Thumb address');
        resolved = {module:module.path, base:module.base.toString(), address:address.toString(),
            rva:c.rva, binary_identity:'user_confirmed_not_verified'};
        return c.thumb ? address.or(1) : address;
    }
    function start(confirmation) {
        if (active) throw new Error('Already active; stop before restarting');
        if (confirmation !== 'SAME BUILD') throw new Error('Confirm identical app/native-library build: SAME BUILD');
        const target = resolve();
        armed = false; sessionGeneration++; count = 0; changedCalls = 0; dropped = 0; queue = []; generation++;
        deadline = Date.now() + c.ttl_seconds * 1000;
        const callbacks = {
            onEnter(args) {
                this.pxo = null;
                if (!active) return;
                if (Date.now() >= deadline || count >= c.max_calls) { stop('limit'); return; }
                const id = ++count, event = {id, phase:'enter', time:Date.now(), thread:this.threadId};
                if (c.calling === 'hits') {
                    if (queue.length < 10) queue.push(event); else dropped++;
                    if (count >= c.max_calls) stop('max-calls');
                    return;
                }
                const snapshot = {event, sessionGeneration, generation, change:armed, edits:JSON.parse(JSON.stringify(edits)), changed:false};
                this.pxo = snapshot;
                try {
                    if (c.calling !== 'hits') {
                        const shift = c.calling === 'instance' ? 1 : 0;
                        event.arguments_before = c.parameters.map((kind,i) => decode(args[i + shift],kind));
                        if (snapshot.change) for (const [index,value] of Object.entries(snapshot.edits.args)) {
                            args[Number(index) + shift] = bits(value); snapshot.changed = true;
                        }
                        event.arguments_after = c.parameters.map((kind,i) => decode(args[i + shift],kind));
                    }
                } catch (error) { stop('callback-error: ' + error.message); }
            },
            onLeave(retval) {
                const snapshot = this.pxo;
                if (!snapshot || snapshot.sessionGeneration !== sessionGeneration) return;
                const event = snapshot.event;
                event.phase = 'leave';
                try {
                    if (c.calling !== 'hits' && c.result !== 'void') {
                        event.return_before = decode(retval, c.result);
                        if (active && armed && Date.now() < deadline && snapshot.change && snapshot.generation === generation && snapshot.edits.return !== null) {
                            retval.replace(bits(snapshot.edits.return)); snapshot.changed = true;
                        }
                        event.return_after = decode(retval, c.result);
                    }
                    if (snapshot.changed) changedCalls++;
                    event.changed = snapshot.changed;
                    if (queue.length < 10) queue.push(event); else dropped++;
                    if (active && count >= c.max_calls) stop('max-calls');
                } catch (error) { stop('callback-error: ' + error.message); }
            }
        };
        if (c.calling === 'hits') delete callbacks.onLeave;
        listener = Interceptor.attach(target, callbacks);
        active = true;
        timer = setTimeout(() => stop('ttl'), c.ttl_seconds * 1000);
        pump = setInterval(flush, 250);
        emit({event:'started', frida:Frida.version, config:c, ...status()});
        return status();
    }
    return {start, stop, status, arm, disarm, clear, setarg, setreturn};
})();
globalThis.pxo = pxo;
rpc.exports = pxo;
