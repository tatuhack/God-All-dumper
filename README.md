# PXOJ Phantom

pxojdumper のダンプを検索し、関数の情報を確認する CLI です。

## 機能

- 保存済みダンプの関数検索とシグネチャ表示
- 実行中の関数の呼び出し監視とログ保存
- 対応する整数・真偽値の引数と戻り値の変更

## 保存済みダンプの検索

Python 3.9 以降と、pxojdumper が出力した Schema 2 JSON が必要です。検索に root 権限や追加パッケージは不要です。ブランチのルートから実行します。

```sh
cd independent/companion
python3 pxoj_phantom.py --version
python3 pxoj_phantom.py list /path/to/dump.json
python3 pxoj_phantom.py list /path/to/dump.json Add --limit 20
```

`/path/to/dump.json` は保存済みダンプのパス、`Add` は検索語の例です。検索語を省略すると一覧を表示します。`--limit` の既定値は 60 件です。結果にはレコード番号と関数のシグネチャが表示されます。

すべての環境で動作するかは保証できません。
