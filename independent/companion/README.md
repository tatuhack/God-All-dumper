# PXOJ Phantom

pxojdumper の JSON から関数を検索し、Frida で呼び出しを観測する CLI コンパニオン。対応する整数・Boolean の引数と戻り値は、明示的に有効化したセッション内で変更できます。

バージョン: 0.1.0。すべての環境で動作するかは保証できません。保護回避、任意の型の変更、全ゲームへの対応は対象外です。

## Features

- pxojdumper v0.2 / schema 2 の JSON を検索。クラス・関数・overload をレコード ID で選択。
- ライブプロセスの module base から RVA を再計算。ELF・ABI・実行可能領域を確認。
- **Hits mode**: 関数に入った回数、時刻、thread ID を記録。
- **Typed mode**: 対応する引数・戻り値の変更前後を観測。
- 引数の個別変更、戻り値変更、解除、JSONL ログ。
- 編集内容は常に待機状態。`ARM` で初めて適用。
- 標準60秒・1000呼び出しで停止。再起動しても自動では編集を有効にしない。
- オフラインの検索・スクリプト出力は Python 標準ライブラリのみ。

これは Magisk / Zygisk モジュールではありません。ZIP は展開して使用します。pxojdumper の既存インストールを置換しません。

## Requirements

- Python 3.9+。ライブ接続には動作する公式 `frida` Python binding が必要。
- 端末側には、そのクライアントと互換性のある `frida-server` と正当な接続権限。
- dump と対象アプリの **native library のビルド・ABIが同一** であること。
- 対象アプリは起動済みで、対象ライブラリがロードされていること。
- 対象アプリの安定性やデータを失っても問題のない、許可されたテスト環境。

### Termux

検索・スクリプト生成は Termux の Python で利用する設計です。

```sh
pkg install python
python pxoj_phantom.py --version
```

ライブ接続には Android/Termux 用に動作する Frida binding が別途必要です。通常の `pip install frida` が端末上で成功するとは限りません。Linux 用 manylinux wheel は Android/Bionic 用ではありません。

既に Frida が動作する環境では確認します。

```sh
python -c 'import frida; print(frida.__version__)'
```

Termux で binding を用意できない場合は、Termux で生成した `hook.js` を、公式 Frida の動作する PC クライアントから使用できます。PC での一般的な導入は `python -m pip install frida frida-tools` です。これは Termux へのインストール保証ではありません。

[Frida公式 Android セットアップ](https://frida.re/docs/android/)に従って、自身で許可した環境を準備してください。本ツールは root 取得、server ダウンロード/起動、SELinux変更、APK改変、保護回避を自動実行しません。server を外部ネットワークに公開しないでください。通常の非root Termuxだけでは、任意の他アプリに接続できません。

## Quick start

ZIPを展開し、`pxoj_phantom.py` と `agent.js` を同じディレクトリに置きます。dump は利用者が権限のある手段で読み取り可能な場所へコピーしてください。

### 1. Search

```sh
python pxoj_phantom.py list dump.json Add
```

例:

```text
[42] [hookable] Assembly-CSharp.dll | Example.Counter::Add(System.Int32) -> System.Int32
```

`42` は `records[]` のインデックスです。関数名が同じでも別のレコード ID で選べます。`no offset` は検索可能ですが hook には使用できません。付属の `examples/sample-dump.json` は操作練習用の架空データで、実アプリには使用できません。

### 2. Observe calls

端末で、すでに接続可能な localhost の Frida server と、対象のPIDを使う例です。

```sh
python pxoj_phantom.py run dump.json \
  --method 42 --arch arm64 --pid 12345 --log session-01.jsonl
```

`--method` を省略すると検索と選択の対話画面が開きます。`SAME BUILD` を入力すると、確認後に観測を開始します。デフォルトは hits mode で、引数や戻り値を解釈しません。

PCからUSB接続する場合は `--usb` を追加します。接続先指定は `--host HOST:PORT`、開発者がホスト上の自作プロセスを試験する場合は `--local` です。PIDは毎回確認してください。パッケージ名からの自動起動はしません。

### 3. Observe and change supported values

**static / instance の違いは必ず確認してください。** pxojdumper v0.2 はメソッドの static 属性を出力しないため、本ツールは推測しません。instance はネイティブの最初の引数が `this`、static は最初から managed parameter という、通常の IL2CPP 生成ABIを前提にします。thunkや独自ABIにはこの前提を使えません。

```sh
python pxoj_phantom.py run dump.json \
  --method 42 --arch arm64 --calling instance \
  --pid 12345 --log session-02.jsonl
```

起動時は引き続き観測のみ。対話コマンドで変更を設定します。

```text
arg 0 100
ret 1
status
arm
ARM
```

- `arg 0 100`: managed parameter の0番目を100にする設定。`this` は数えない。
- `ret 1`: 戻り値を1にする設定。
- `status`: 関数、適用先アドレス、回数、設定、状態を表示。
- `arm` → `ARM`: 設定した変更を以後の呼び出しに適用。
- `disarm`: 変更を止め、観測は継続。
- `clear`: 解除して設定を消去。
- `stop` / `quit` / Ctrl+C: hook解除とセッション終了を試みる。

`arg` / `ret` を変更するたびに、適用状態はOFFへ戻ります。適用前にもう一度 `arm` が必要です。

起動引数で設定のみ準備することもできます。

```sh
python pxoj_phantom.py run dump.json --method 42 --arch arm64 \
  --calling instance --arg 0=100 --ret 1 --pid 12345 --log session-03.jsonl
```

これも自動では適用しません。`--ttl 120 --max-calls 5000` で上限を変更できます。許容範囲は1–3600秒、1–1000000回です。制限は安全性の保証ではなく、暴走防止の補助です。プロセス停止やJS runtimeの停止中はタイマーが遅れる場合があります。

### 4. Export a standalone Frida script

```sh
python pxoj_phantom.py export dump.json --method 42 --arch arm64 \
  --calling instance --arg 0=100 -o hook.js
frida -U -p 12345 -l hook.js
```

ロードだけではhookを設置しません。Frida REPLで開始します。

```js
pxo.start('SAME BUILD')
pxo.status()
pxo.setarg(0, 100)
pxo.setreturn(1)
pxo.arm('ARM')
pxo.disarm()
pxo.stop()
```

生成物にdumpの関数名・module名・選択内容が含まれます。共有前に内容を確認してください。Python runner はJSONLを保存しますが、単体JSではFridaのメッセージとして出力するため、別途クライアント側でログを保存します。

## Supported value types

型名が次のいずれかで、**すべての引数と戻り値**が対応範囲内の関数だけをtyped modeで扱います。戻り値は `System.Void` も許可しますが、変更できません。

- `System.Boolean`: 0 / 1、またはCLI入力の true / false。
- `System.SByte`, `System.Byte`: signed / unsigned 8-bit。
- `System.Int16`, `System.UInt16`, `System.Char`: signed / unsigned 16-bit。Char入力は数値コード単位。
- `System.Int32`, `System.UInt32`: signed / unsigned 32-bit。

typed mode は Linux/Android の `arm64` と `x64` のみ。managed parameter と `this` が一般レジスタ8個（arm64）/6個（x64）に収まる関数に限定し、隠し `MethodInfo*` は読み書きしません。

**対象外:** float/double、64-bit整数、enum、文字列、object、配列、pointer、ref/out、struct、generic、可変引数、独自呼出規約。これらを含む関数は hits mode で呼び出しだけを観測できます。ARM32/Thumbとx86もhits modeのみです。一般レジスタの整数をfloatの実値として表示するような変換は行いません。

既知の同一module/RVAを持つ複数レコードは、typed modeでは拒否します。ただしpartial dumpやruntimeのコード共有により、共有先を完全には把握できません。generic名が明確でない場合もあり、型チェックだけでABIの正しさは証明できません。

## Safety and limitations

- **dumpにビルドIDやコードのfingerprintはありません。** ELF形状・アドレス範囲検証は同じバイナリである証明ではありません。アプリ更新後は必ず新しいdumpを取得してください。
- ELFの先頭 `PT_LOAD` がfile offset 0でpage-aligned、headerがmodule baseから読める通常の配置に限定します。特殊なELF配置は拒否します。
- オフセットは関数本体ではなく共有実装やthunkを示す可能性があります。メソッド単位の分離を保証しません。
- 観測にもコードへのInterceptor設置が必要です。読み取り観測でもクラッシュ・処理遅延は起こり得ます。
- 引数の変更は関数の処理そのものに影響します。戻り値の変更は処理終了後なので、関数の副作用を取り消しません。
- `disarm` / `stop` は今後の変更を止める操作です。変更済み引数、保存データ、送信済み通信などは元に戻せません。実行中の戻り値編集は解除後に適用しません。
- hits modeは関数入口で記録。typed modeの詳細ログは通常のreturn時のみで、例外・unwind・終了しない関数の詳細は欠落し得ます。`count` は入口回数で、`changed_calls` はreturnまで観測できた編集呼び出し数です。
- ログは最大10イベントを250msごとにまとめます。高頻度時はイベントを捨て、`dropped_logs` に集計します。すべての呼び出しを保存する監査用トレーサではありません。編集自体はログの間引きとは独立して適用されます。
- ログ保存失敗や切断時は、入力待ちを中断して解除を試みます。通信が失われた時の解除は保証できないため、target-side TTLも設けています。
- 同時に1つの関数を対象とします。field編集、メモリ検索、恒久patch、保存値の自動復元はありません。
- 生成JSやdumpを編集して保護を外さないでください。サーバーや第三者のデータ、対人戦、競争サービスの不正操作に使用しないでください。

## Development and tests

```sh
python3 -m unittest discover -s tests -v
node tests/agent_test.cjs
```

FridaとCコンパイラを用意した開発機で、自作のネイティブfixtureへ接続する追加テスト:

```sh
python3 tests/live_smoke.py
```

これはLinux x64用で、Android/Unityの試験ではありません。[TEST_RESULTS.md](TEST_RESULTS.md) に通過・未実行・失敗の区別を記録しています。

## References

- [pxojdumper v0.2](https://github.com/tatuhack/God-All-dumper/tree/pxojdumper-independent)
- [Frida JavaScript API](https://frida.re/docs/javascript-api/)
- [Frida 17 API migration](https://frida.re/news/2025/05/17/frida-17-0-0-released/)

modern `Process.enumerateModules()`、NativePointer instance reads、`Interceptor.attach()` を使用し、削除されたstatic Module APIやJava bridgeには依存しません。公式Fridaコードやバイナリは本パッケージに同梱しません。

## License

[0BSD](LICENSE)。PXOJ Phantomは独立した補助ツールで、Frida projectとの提携・公認を意味しません。
