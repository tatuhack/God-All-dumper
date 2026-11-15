# pxojdumper

新しく記述した実験的な Unity IL2CPP メタデータ収集モジュールです。対象を設定してアプリを再起動すると、取得可能な型・メソッド・フィールド情報を保存します。以前の名称変更版とは別実装・別成果物で、既存 dumper と同一機能ではありません。

## 現在の機能

- 指定パッケージのメインプロセスだけを対象にします。未設定なら収集しません。
- 標準の動的ローダーと公開 IL2CPP export を使い、最大約60秒起動待ちします。
- アセンブリ／型／namespace（nested 型は A+Inner のように外側の型名と一緒に記録し、レコード内の type_id でも識別）、メソッド名・戻り値型・引数型、フィールド名・型・runtime が返す offset/flags を収集。
- JSON と、読みやすいコメント形式の `.cs` 一覧を作成。元ソースやコンパイル可能な C# の復元ではありません。
- 20万レコード上限と、レコード間で約60秒を確認する協調的な期限。IL2CPP API 内の停止や遅延を強制中断するものではありません。出力の合計64MiBもレコード間で確認し、超えたら収集を止めます（1レコード分だけ超過する場合があります）。部分出力は JSON の `partial` に記録します。
- root shell 用の設定コマンド、Action、KernelSU 互換 bridge 用 WebUI。

**ネイティブメソッドの関数アドレス／RVA／オフセットは未対応です。** 標準 export だけでは確定できない情報を、private な MethodInfo 配置の推測で補いません。各メソッドの `native_address` / `native_offset` は `null` です。フィールド offset は runtime API の返り値で、static/literal フィールドの場合に単純なインスタンス内オフセットとして扱わないでください。

## 必要な環境と未対応事項

**対象アプリのプロセス内で実行します。API の非互換性や不安定な runtime により、アプリのクラッシュ・停止・起動遅延・ストレージ消費が起きる可能性があります。重要なデータのある対象でいきなり試さず、許可されたテスト環境で確認してください。プロセス内障害を隔離する仕組みはありません。**

- 配布ZIPのインストーラはMagisk形式です。KernelSU/APatchへのインストール互換性は未検証で、対応を保証しません。WebUIはKernelSU互換bridge向けに実装したものですが、インストール対応を意味しません。
- Zygisk API v5 対応環境（公式 SDK の目安は Magisk 27以降）。通常の非root Termuxだけでは動きません。
- IL2CPP export が公開され、標準 `dlopen(..., RTLD_NOLOAD)` で参照できる対象が必要です。export 隠蔽、独自 runtime、loader namespace 制限等では失敗します。回避処理はありません。
- Cocos2d-x/UE4/UE5、Mono、コードやassets復元、定数値復元、属性/property/継承の完全復元、x86環境でのARM変換ロードは未対応です。
- 対象プロセスを止めないため、一貫したスナップショットではありません。アプリ起動後に追加された型をすべて拾う保証はありません。
- **Android 実機のインストール・WebUI・ゲーム起動・実際の出力は未検証です。** 同一動作／すべてのゲームへの互換性は保証しません。自作または解析許可のある対象で検証してください。

## ビルド

公式 Android NDK r28c と CMake 4.1.2 を用意し、Python 3 で実行します。

```sh
python3 tools/build.py --ndk /path/to/android-ndk-r28c --cmake-bin /path/to/cmake/bin
```

Android API23向けの4ABIを生成し、`out/pxojdumper-0.1.0-independent.zip` にまとめます。C++ STL は使わず、公式 SDK が必要とする Android system libstdc++ のみに依存します。ビルドは端末設定やインストールを変更しません。

## 使い方

1. この版と以前の版は同じモジュールIDを使うため、どちらを入れるか確認してください。インストールすると同IDの既存版を更新する可能性があります。自動インストールはしません。
2. 対応root managerでモジュールZIPをインストールし、必要な再起動を行います。
3. root shellで対象を指定します（Termuxでは自分でroot shellを開く必要があります）。

```sh
/data/adb/modules/pxojdumper/pxojdumper set com.example.game
/data/adb/modules/pxojdumper/pxojdumper show
```

対象アプリを再起動すると、アプリの専用ディレクトリに時刻・PID付きで保存します。

```text
/data/data/<package>/files/pxojdumper/dump-<timestamp>-<pid>.json
/data/data/<package>/files/pxojdumper/dump-<timestamp>-<pid>.cs
```

既存の成功出力を上書きしません。失敗理由は `pxojdumper` タグの Android logcat に出します。共有Downloadへの自動コピーは行いません。WebUIの停止、または次のコマンドは次回起動以降の収集を止めます。進行中の収集を強制終了しません。

```sh
/data/adb/modules/pxojdumper/pxojdumper off
```

## 検証

```sh
python3 -m unittest discover -s tests -v
node tests/webui_test.mjs
```

テストの runtime は独自の模擬ライブラリです。実際の Unity の互換性検証ではありません。詳細は TEST_RESULTS.md。

## 出典とライセンス

収集処理・UI・設定・テストは本版向けに新規記述しています。外部コードは公式Zygisk SDKヘッダーのみで、元の著作権表示と0BSD許諾を保持しています。詳細は THIRD_PARTY_NOTICES.md。過去の調査では他ツールを閲覧しているため、法的なクリーンルーム開発を保証するものではありません。
