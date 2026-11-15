import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const html = fs.readFileSync(new URL('../template/module/webroot/index.html', import.meta.url), 'utf8');
const script = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1].replace(/^\s*import .*;$/m, '');
assert.match(html, /<title>pxojdumper WebUI<\/title>/);

async function setup({bridge = true, errno = 0} = {}) {
  const elements = Object.fromEntries(['pkgInput', 'saveBtn', 'currentPkg'].map(id => [id, {
    disabled: false, textContent: '', value: '', listeners: {},
    addEventListener(event, callback) {this.listeners[event] = callback;}
  }]));
  const calls = [], toasts = [];
  let ready;
  const context = {
    document: {getElementById: id => elements[id], addEventListener: (_, cb) => ready = cb},
    isKsuWebui: () => bridge, enableEdgeToEdge: async () => {},
    toast: value => toasts.push(value), console,
    exec: async command => {calls.push(command); return {errno, stdout: 'com.test.current\n', stderr: 'mock'};}
  };
  vm.runInNewContext(script, context);
  await ready();
  return {elements, calls, toasts};
}
const missing = await setup({bridge: false});
assert.equal(missing.elements.saveBtn.disabled, true);
assert.equal(missing.calls.length, 0);
const good = await setup();
assert.equal(good.elements.currentPkg.textContent, 'com.test.current');
assert.equal(good.calls[0], 'getprop persist.pxojdumper.package');
good.elements.pkgInput.value = 'com.test.new';
await good.elements.saveBtn.listeners.click();
assert.equal(good.calls[1], 'setprop persist.pxojdumper.package com.test.new');
assert.equal(good.elements.saveBtn.disabled, false);
good.elements.pkgInput.value = 'com.test;id';
await good.elements.saveBtn.listeners.click();
assert.equal(good.calls.length, 2);
assert.equal(good.toasts.at(-1), 'Invalid package name');
const failed = await setup({errno: 1});
failed.elements.pkgInput.value = 'com.test.new';
await failed.elements.saveBtn.listeners.click();
assert.equal(failed.elements.saveBtn.disabled, false);
assert.equal(failed.toasts.at(-1), 'Failed to save config!');
console.log('WebUI mocks passed: missing bridge, read, save, invalid input, failed save');
