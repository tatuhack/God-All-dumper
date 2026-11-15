# pxojdumper

Android の Unity IL2CPP ゲームを、許可された環境で起動時に解析する Zygisk モジュールです。既存の Zygisk-Il2CppDumper を基にした名称変更版で、独自開発の解析エンジンではありません。出典・変更点は [NOTICE.md](NOTICE.md) に記載しています。

## 現在の検証状態

ソースの名称・設定変更、ホスト上の回帰テスト、公式 NDK/CMake を使う **4 ABI の Android ネイティブビルドとモジュール ZIP 作成が完了**しています。**インストール・実機動作は未検証**です。Gradle 経由の全ビルドは未完了です。ソース ZIP とインストール用 ZIP は別です。

## 機能と対象

- 上流の実行時 IL2CPP API による `dump.cs` 出力を保持。
- 型・メソッド・フィールド等の出力は上流実装と対象ランタイムに依存します。
- 動的な対象パッケージ切替、WebUI、root manager の Action、定数値／ストリーミング出力などの上流機能を保持。
- Unity IL2CPP 専用です。Cocos2d-x、UE4、UE5 の解析ツールではありません。
- 任意の暗号化・難読化・独自 IL2CPP 改変への対応や、全 Unity バージョンとの互換性を保証しません。

## 必要な環境

Zygisk を有効にした対応 root 環境が必要です（Magisk、または対応する Zygisk 環境を備えた KernelSU/APatch）。通常の非 root Termux だけでは実行できません。自分が所有する、または解析を許可されたアプリにのみ使用してください。保護回避の追加手順は含めていません。

## ビルド

### 検証済み: NDK/CMake から直接ビルド

公式 Android NDK r28c (28.2.13676358) と CMake 4.1.2 を展開し、次のパスを自分の環境に合わせて設定します。Python 3 も必要です。ビルドスクリプトはダウンロード・インストール・端末へのフラッシュを自動実行しません。

```sh
export ANDROID_NDK_HOME=/path/to/android-ndk-r28c
export CMAKE_BIN=/path/to/cmake/bin
./tools/build_native.sh
```

arm64-v8a / armeabi-v7a / x86 / x86_64 を Android API 23 向けにビルドし、`out/pxojdumper-v1.6.1-6-release.zip` を生成します。C++ ランタイムは静的リンクし、追加の libc++_shared.so 配布を不要にしています。パッケージには元のライセンス、帰属表示、Zygisk が要求するファイル配置を保持します。

### 上流から保持: Gradle 経由（未完了）

上流の指定を保持しています: JDK 17 以降（Gradle/AGP の要件も確認）、Gradle 9.4.1、Android Gradle Plugin 9.2.0、Android SDK 37、NDK 28.2.13676358、CMake 4.1.2。この経路の互換性を含む全ビルドは未検証です。今回の Gradle 試行はラッパー配布物のダウンロードで停止したため、上の直接ビルドを使用しました。

```sh
./gradlew :module:assembleRelease
```

成功すると `out/pxojdumper-v1.6.1-6-release.zip` が生成されます。ソースアーカイブを root manager でインストールしないでください。公式上流の更新 URL は外してあるため、自動的に別製品の ZIP に更新されません。

## 利用手順

ビルドしたモジュールを自分で root manager にインストールして再起動した後、root shell で対象を設定します。

```sh
setprop persist.pxojdumper.package com.example.game
```

Termux の場合は root shell を利用できる環境が必要です。対象ゲームを再起動すると、上流と同じ場所に出力します。

```text
/data/data/<GamePackageName>/files/dump.cs
```

WebUI や Action ボタンでも設定を確認できます。既存の `persist.il2cppdumper.package` は引き継ぎません。モジュール ID が違うため旧モジュールと共存できますが、同じ対象に両方を有効にしないでください。既存モジュールを自動削除する処理はありません。

以前の別案にあった `/sdcard/Download/Dumpgod` 保存や Termux 単体ダンプは、この「上流と同じ動作」の版では追加していません。

## ソース検証

```sh
python -m unittest discover -s tests -v
node tests/webui_test.mjs
```

これらは Android のネイティブビルドや実機検証を代替しません。詳細は TEST_RESULTS.md を参照してください。

## ライセンスと出典

[MIT License](LICENSE)。Rikka、Perfare、codehasan、xDL / HexHacking Team、および KernelSU WebUI ヘルパーの帰属・ライセンスを保持しています。名称変更後も、Zygisk API 名、必須の `zygisk/` 配置、上流コードの著作権表示は消していません。詳細は [NOTICE.md](NOTICE.md) と [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) を参照してください。
