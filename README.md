# PXOJ Seeker (Offline)

保存済みの pxojdumper ダンプ（Schema 2 JSON）を検索・比較する CLI です。Python 3.9 以降の標準ライブラリだけで動きます。ネットワークや root 権限は不要です。

## 使い方

```sh
python3 pxoj_seeker.py --version
python3 pxoj_seeker.py info examples/sample-dump.json
python3 pxoj_seeker.py search examples/sample-dump.json speed damage
python3 pxoj_seeker.py show examples/sample-dump.json 1
python3 pxoj_seeker.py compare examples/sample-dump.json 1 2 3
```

`search` は名前・型・名前空間から候補を検索します。`show` は1件の詳細、`compare` は2〜12件の候補を表示します。レコード ID は各ダンプ内で有効です。すべてのコマンドで `--help`、出力コマンドでは `--json` が使えます。

RVA、ELF 内ファイル位置、ダンプ取得時のアドレス、フィールドのオフセットは別の値です。表示は保存時点のデータに基づきます。この版は実行中のプロセスに接続せず、他ツール向けの実行スクリプトや引き継ぎファイルも生成しません。

## テスト

```sh
python3 -m unittest discover -s tests -v
```

同梱のサンプルは合成データです。すべての環境で動作するかは保証できません。
