# pxojdumper

Android 向けの Unity IL2CPP ランタイム解析モジュール。対象アプリを指定し、型・メソッド・フィールド情報と、検証条件を満たすネイティブオフセットを出力します。

> このREADMEは [pxojdumper v0.2.0](https://github.com/tatuhack/God-All-dumper/tree/pxojdumper/independent) の機能と手順を説明しています。`main` には旧実装を保持しています。

## 機能

- アセンブリ・namespace・nested 型、メソッド名・戻り値型・引数型の収集。
- フィールド名・型・runtime が返すオフセットと属性フラグ。
- 対応レイアウトと実行可能領域を照合できたメソッドの実行時アドレス、RVA、ELF仮想アドレス、ファイルオフセット。
- root shell コマンド、Action、KernelSU互換bridge向けWebUI。
- 時刻・PID付きの JSON と `.cs` コメント一覧。既存の成功出力を上書きしません。

## 対応環境

Android API23以降、arm64-v8a / armeabi-v7a / x86 / x86_64 をビルド対象にしています。Zygisk API v5対応のroot環境（公式SDKの基準はMagisk27以降）と、公開IL2CPP exportへ標準ローダーからアクセスできるUnity IL2CPPアプリが必要です。

インストーラは Magisk 形式です。通常の非 root Termux 単体では動作しません。

## ビルド

公式 Android NDK r28c、CMake4.1.2、Python3 を用意します。

```sh
git clone https://github.com/tatuhack/God-All-dumper.git
cd God-All-dumper
git switch pxojdumper
cd independent
python3 tools/build.py \
  --ndk /path/to/android-ndk-r28c \
  --cmake-bin /path/to/cmake/bin
```

生成物は `independent/out/pxojdumper-0.2.0-independent.zip`（リポジトリルート基準）です。ソースアーカイブではなく、このモジュールZIPを対応root managerへ渡してください。ビルド処理は端末へのインストールや再起動を行いません。

## 使い方

モジュールをインストールし、必要な再起動を行った後、root shellで対象を設定します。

```sh
/data/adb/modules/pxojdumper/pxojdumper set com.example.game
/data/adb/modules/pxojdumper/pxojdumper show
```

対象アプリを再起動すると、アプリ専用ディレクトリへ保存します。

```text
/data/data/<package>/files/pxojdumper/dump-<timestamp>-<pid>.json
/data/data/<package>/files/pxojdumper/dump-<timestamp>-<pid>.cs
```

次回起動からの収集を止めるには:

```sh
/data/adb/modules/pxojdumper/pxojdumper off
```

同じモジュールIDの既存インストールがある場合は更新・置換される可能性があります。`off` は進行中の処理を強制終了しません。

## オフセットの扱い

ネイティブオフセットは、2種類の対応するMethodInfo構造を公開APIの返り値と照合し、初期メモリマップとELF実行可能セグメントを確認して出力します。`native_offset` は最小PT_LOAD仮想アドレスを基準としたRVAで、ELF仮想アドレスやファイルオフセットとは別です。

成功時も `conditional_on_runtime_layout` と記録します。任意の改変runtimeでの意味的な正しさや元の関数本体であることを証明するものではなく、generic共有実装やthunkが返る場合があります。条件を満たさない値は `null` と理由を記録します。

詳細: [ネイティブオフセット仕様](https://github.com/tatuhack/God-All-dumper/blob/pxojdumper/independent/docs/NATIVE_OFFSETS.md)

## 制限と検証状況

4 ABI のネイティブビルドとホストテストは通過しています。すべての環境で動作するかは保証できません。

対象プロセス内で実行するため、非互換APIや不安定なruntimeではクラッシュ・停止・起動遅延が起きる可能性があります。許可されたテスト環境で使用してください。取得時のマップ変更を完全には追跡しません。

Cocos2d-x、UE4/UE5、Mono、assets復元、暗号解除、保護回避、完全なSDK/ソース復元には対応しません。`.cs` はコンパイル可能な元ソースではありません。20万レコード上限と、レコード間の約60秒・合計64MiB確認は協調的制限であり、処理時間の強制上限ではありません。

[詳しい使用方法](https://github.com/tatuhack/God-All-dumper/blob/pxojdumper/independent/README.md) · [テスト結果](https://github.com/tatuhack/God-All-dumper/blob/pxojdumper/independent/TEST_RESULTS.md)

## ライセンス

v0.2.0 のソースは [0BSD](https://github.com/tatuhack/God-All-dumper/blob/pxojdumper/independent/LICENSE)。公式Zygisk SDKヘッダーの著作権・許諾は保持しています。[外部コードと技術参照](https://github.com/tatuhack/God-All-dumper/blob/pxojdumper/independent/THIRD_PARTY_NOTICES.md)を参照してください。

`main` に保持している以前のソースには、その [LICENSE](LICENSE)、[NOTICE.md](NOTICE.md)、[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) が適用されます。v0.2.0 のライセンスは旧実装には適用されません。
