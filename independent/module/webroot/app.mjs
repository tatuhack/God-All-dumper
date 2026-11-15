export function validPackage(value) {
  return value.length <= 90 && /^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$/.test(value);
}
let serial = 0;
export function shell(command, host = globalThis) {
  return new Promise((resolve, reject) => {
    if (typeof host.ksu?.exec !== 'function') { reject(new Error('対応する root manager の WebUI から開いてください。')); return; }
    const key = `pxo_response_${++serial}`;
    const cleanup = () => { clearTimeout(timer); delete host[key]; };
    const timer = setTimeout(() => { cleanup(); reject(new Error('応答がありません。設定を再確認してください。')); }, 10000);
    host[key] = (code, output, error) => {
      cleanup();
      if (Number(code) === 0) resolve(String(output ?? '').trim());
      else reject(new Error(String(error || '設定操作に失敗しました。')));
    };
    try { host.ksu.exec(command, '{}', key); } catch (error) { cleanup(); reject(error); }
  });
}
export async function bind(doc, execute = shell) {
  const input=doc.getElementById('package'), save=doc.getElementById('save'), off=doc.getElementById('off'), status=doc.getElementById('status');
  const busy = value => {save.disabled=value;off.disabled=value;input.disabled=value;};
  async function apply(value) {
    busy(true);
    try {
      await execute(`setprop persist.pxojdumper.package '${value}'`);
      status.textContent=value ? `保存しました: ${value}。対象アプリを再起動してください。` : '次回起動からの収集を停止しました。';
      input.value=value;
    } catch (error) {status.textContent=error.message;} finally {busy(false);}
  }
  save.addEventListener('click', () => {
    const value=input.value.trim();
    if (!validPackage(value)) {status.textContent='パッケージ名を確認してください。';return;}
    return apply(value);
  });
  off.addEventListener('click', () => apply(''));
  busy(true);
  try {const value=await execute('getprop persist.pxojdumper.package');input.value=value;status.textContent=value?`現在の対象: ${value}`:'対象は未設定です。';busy(false);}
  catch(error){status.textContent=error.message;}
}
if (typeof document !== 'undefined') bind(document);
