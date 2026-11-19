# PXOJ Diff

pxojdumper の Schema 2 JSON を比較する CLI です。関数の対応候補、RVA の変化、片方のダンプにしかない関数、曖昧な一致を表示します。

バージョン: 0.1.0。Python 標準ライブラリで動作する CLI です。ZIP を展開して使用します。すべての環境で動作するかは保証できません。Magisk モジュールではありません。

## できること

- assembly、namespace、宣言型、メソッド名、戻り値型、引数の数と全型が一致し、両ダンプで一意な候補を対応付け。
- `old ID -> new ID`、RVAの旧値・新値・差分、取得可否の変化を表示。
- ELF仮想アドレス、ELFファイルオフセット、ELF最小仮想アドレスの変化を別に記録。
- 同名シグネチャの重複、不完全な型名や引数一覧、同名クラスの重複を保留。
- 全件JSONレポート、表示件数を制限したテキストレポート。
- 旧版のIDまたはSeeker選択ファイルから、新版用のSeeker選択ファイルを作成。

自動接続、フック、書き換え、保護回避、元ソース復元は行いません。比較対象はメソッドです。型レコードは宣言クラスの検証に使い、フィールドの差分はこの版では出しません。

## Termuxで開始

必要: Python 3.9以降。Diff自体にroot、Frida、pipパッケージは不要です。入力dumpを読める権限は必要です。

```sh
pkg install python unzip
unzip pxoj-diff-0.1.0.zip
cd pxoj-diff-0.1.0
python pxoj_diff.py --version
python pxoj_diff.py compare examples/old-dump.json examples/new-dump.json
```

サンプルは**架空の検証データ**です。ゲームから収集した結果ではありません。サンプルでは `GetSpeed` が旧ID 1から新ID 2へ対応し、RVAが `0x2000 -> 0x2080` と変わります。

実際には、更新前・更新後に取得したJSONを、利用者が読み取り可能な場所へ置いてください。Diffは保護されたアプリ領域から自動コピーしません。通常の非root Termuxでできるのは、取得済みJSONの比較です。元のダンプ収集にはpxojdumper側の要件が適用されます。

## 1. 比較する

```sh
python pxoj_diff.py compare old.json new.json
python pxoj_diff.py compare old.json new.json --changed-only
python pxoj_diff.py compare old.json new.json --limit 30
python pxoj_diff.py compare old.json new.json -o diff.txt
python pxoj_diff.py compare old.json new.json --format json -o diff.json
```

- `old.json` は更新前、`new.json` は更新後です。同じABI同士で比較してください。
- `--changed-only` は、RVAも他のオフセット証拠も変わらない対応行をテキスト表示から省略します。取得不可、曖昧、旧版のみ・新版のみの情報は残します。ASLRによる実行時アドレス変化だけでは表示対象になりません。
- テキストは各区分の先頭100件が既定です。`--limit` は1〜10000。JSONは全件で、表示用オプションによってデータを省きません。
- JSONは機械処理向けです。`--format json` を標準出力に出す場合、標準出力はJSONだけです。
- `-o` の出力先が既にある場合は停止します。入力や過去の結果を上書きしません。別のファイル名を指定してください。
- すべてのIDは、その入力JSONの `records[]` のindexです。旧IDを新ダンプへそのまま使わないでください。

## 2. 結果の読み方

| 区分 / 状態 | 意味 |
|---|---|
| `matches` | 完全なメタデータシグネチャが一意に一致した候補 |
| `rva_changed` | 条件を満たす候補間でRVAの数値が変化 |
| `rva_unchanged` | RVAの数値は同じ。実装や挙動の同一性は未確認 |
| `became_available` / `became_unavailable` | ネイティブ証拠の取得可否が変化 |
| `unavailable_both` | 両方でRVA比較に使える証拠がない |
| `module_incomparable` | モジュールの対応を設定した基準で判断できない |
| `thumb_mode_changed` | ARM Thumbモード情報が変わり、RVA差分を保留 |
| `old_only` / `new_only` | 旧ダンプだけ・新ダンプだけに現れたシグネチャ |
| `ambiguous` | シグネチャが重複。勝手に1対1へ対応付けない |
| `unresolved_old` / `unresolved_new` | 型名などの欠損・損失・重複、引数一覧の途中切れなど |

**`old_only` / `new_only` は削除・追加の候補です。** 名前変更、シグネチャ変更、難読化、収集範囲の違いでも出ます。`partial=true` のダンプでは、未収集の関数や重複候補がありえます。完全なダンプと表示されても、ゲーム内の全コードを網羅した保証にはなりません。

同一module/RVAを共有するレコード数も記録します。generic共有実装やthunkなどでは、1つのアドレスが1つのメソッド専用とは限りません。

### モジュールの比較基準

既定は `--module-policy basename-unique` です。

1. 完全なmoduleパスが一致すれば `exact_module_path`。
2. パスが違っても、`libil2cpp.so` などのbasenameが一致し、両ダンプ内でそれぞれ1つのパスにしか現れなければ `unique_basename_heuristic`。
3. それ以外は `module_incomparable`。

Androidのアプリ更新でインストール先ディレクトリが変わる場合を扱います。**ファイル名の対応に基づく推定であり、同じバイナリの証明ではありません。** より厳しく完全なパス一致だけを使う場合:

```sh
python pxoj_diff.py compare old.json new.json --module-policy exact
```

RVAは各ELFの最小PT_LOAD仮想アドレスを基準にした値です。実行時VA、ELF仮想アドレス、ファイルオフセットとは別物です。Diffはdump時のVAやIDでメソッドを対応付けず、アドレスの差をRVAとして扱いません。ELF最小仮想アドレスが変わるとRVA差分の解釈も変わるため、レポートで別途示します。

## 3. 新版の候補をSeekerへ渡す

まず対応行と新しいシグネチャを確認してください。次の `1` は説明用の旧IDです。

```sh
python pxoj_diff.py handoff old.json new.json --old-id 1 -o new-selection.json
```

旧版で保存していたSeeker選択ファイルを使う場合:

```sh
python pxoj_diff.py handoff old.json new.json --selection old-selection.json -o new-selection.json
```

- 一意な完全シグネチャ一致がなければ出力しません。
- 元の選択ファイルは、旧ダンプの**正確なバイト列のSHA-256**と照合します。JSON整形だけの変更でも別ファイルとして拒否します。
- 新しい選択ファイルは、新ダンプのSHA-256と新IDに結び付けます。旧RVAや旧フックスクリプトを移植しません。
- 選択はメタデータ候補の記録です。新RVAが取得不可でも選択ファイルを作成できます。後段のSeeker/Phantomがnative証拠を再検証し、取得不可ならexport/runを拒否します。
- partialの場合は警告します。省略された重複シグネチャや共有実装を除外できません。

PXOJ Seeker 0.1.0は別途、先に配布されたZIPを使用します。DiffにはSeeker/Phantomを同梱していません。Seekerディレクトリから、新ダンプと選択ファイルの実際のパスを指定します。

```sh
python pxoj_seeker.py show /path/to/new.json NEW_ID
python pxoj_seeker.py export /path/to/new.json \
  --selection /path/to/new-selection.json \
  --arch arm64 -o new-hook.js
```

`NEW_ID` はhandoff出力に表示された新IDへ置き換えます。`arm64` も実際の対象ABIに合わせて指定します。DiffはABIを検出しません。exportはスクリプト生成のみで、このコマンド例では接続しません。ライブ観測を行う場合はSeeker/PhantomのREADMEに従い、新しい実行バイナリ・ABIがdumpと一致することを別途確認してください。**旧版のスクリプトをそのまま新版へ読み込まないでください。**

## 一致の限界

- 名前や完全シグネチャが一致しても、同じゲーム上の役割・同じ動作・同じ関数本体を証明しません。
- schema 2にはバイナリハッシュ、ABI、メソッドtoken、generic arity、static/instance flagsがありません。同じ表示名でも別の実体の場合があります。
- 名前が変わった関数を、アドレスや似た名前から自動で推測しません。`old_only` / `new_only` をSeekerで確認してください。
- 4096 UTF-8 bytes以上のシグネチャ文字列、置換文字、収集時の特殊placeholderなどは保守的に除外します。正当な名前でも除外される場合があります。
- native証拠は収集時のlayout/mapping検証と数値整合性だけです。Diff自体は実ELF、端末メモリ、ライブプロセスを検証しません。
- メモリ上で2つのダンプとレポートを組み立てます。入力は各70MiB/20万レコード以下ですが、RAM使用量は入力サイズより大きくなります。低メモリ端末では小さいダンプを使ってください。ストリーミング比較ではありません。
- 入力はローカルJSONのみで、ネットワーク送信や任意プラグインの読み込みはありません。端末への表示では制御文字をescapeします。

## テスト・再パッケージ

```sh
python -m unittest discover -s tests -v
python package.py pxoj-diff-repacked.zip
```

単体ZIPでは、元collectorのソースを必要とする2テストがskipになります。他のテストは標準ライブラリのみです。collector→Diff→Seeker→Phantomの連携テストは元ソース配置で実行済みです。結果と未検証項目は [TEST_RESULTS.md](TEST_RESULTS.md) を参照してください。

CLI終了コード: 正常 `0`、入力・ファイルエラー `2`、中断 `130`。差分の有無は終了コードに影響しません。出力中断やディスク障害時には途中の出力が残る可能性があります。再実行は別の出力名を使ってください。

## ライセンス

[0BSD](LICENSE)。比較にはPython標準ライブラリのみを使用します。
