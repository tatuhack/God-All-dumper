# pxojdumper

Android 向けの Unity IL2CPP ランタイム解析モジュール。対象アプリを指定し、起動時に型・メソッド・フィールド情報を JSON とテキスト一覧へ出力します。

バージョン: 0.2.0。 ネイティブオフセットは対応する構造と実行可能領域を検証できた場合に限って出力し、不明な値を推測で埋めません。

## 機能

- アセンブリ、namespace、型名、nested 型名、メソッド名、戻り値型、引数型。
- フィールド名・型・runtime が返すオフセットと属性フラグ。
- 条件を満たすメソッドのネイティブアドレス、RVA、ELF 仮想アドレス、ELF ファイルオフセット。
- パッケージ指定による収集、root shell コマンド、Action ボタン、KernelSU 互換 bridge 向け WebUI。
- 時刻・PID付きファイルで保存。レコード上限と協調的な時間・出力容量制限。

出力の `.cs` はメタデータを読みやすく並べたコメント形式の一覧です。コンパイル可能な C# ソースや、元の実装を復元するものではありません。

## 動作要件

- Android API 23 以降。ビルド対象: arm64-v8a、armeabi-v7a、x86、x86_64。
- Zygisk API v5 に対応する root 環境。公式 SDK の基準は Magisk 27 以降です。
- 公開 IL2CPP export があり、標準ローダーからアクセス可能な Unity IL2CPP アプリ。
- ネイティブオフセットの収集には、対象プロセス自身の `/proc/self/mem` と `/proc/self/maps` の読み取りが必要です。拒否された場合は回避せず、そのメソッドのオフセットを取得不可として記録します。

ZIP は Magisk 形式です。WebUI の bridge 対応は、インストーラやランタイムの互換性保証ではありません。通常の非 root Termux 単体では利用できません。

## ビルド

Python 3、公式 Android NDK r28c、CMake 4.1.2 を用意します。

```sh
python3 tools/build.py \
  --ndk /path/to/android-ndk-r28c \
  --cmake-bin /path/to/cmake/bin
```

4 ABI のネイティブライブラリと、次のインストール用 ZIP を生成します。

```text
out/pxojdumper-0.2.0-independent.zip
```

ビルドは端末へのインストール、再起動、アップロード、セキュリティ設定変更を行いません。C++ STL は使用せず、公式 SDK が必要とする Android system libstdc++ にリンクします。

## インストールと設定

1. ソース ZIP ではなく、ビルドしたモジュール ZIP を root manager へ渡します。
2. 必要な再起動後、root shell で対象を設定します。
3. 対象アプリを再起動します。

```sh
/data/adb/modules/pxojdumper/pxojdumper set com.example.game
/data/adb/modules/pxojdumper/pxojdumper show
```

対象を設定しない限り収集しません。Termux を使う場合も、利用者自身が許可された root shell を用意する必要があります。

収集を停止するには:

```sh
/data/adb/modules/pxojdumper/pxojdumper off
```

`off` は次回起動からの収集を無効にします。進行中の収集を強制終了するものではありません。モジュール ID は `pxojdumper` なので、同じ ID の既存インストールがある場合は更新・置換される可能性があります。

## 出力

```text
/data/data/<package>/files/pxojdumper/dump-<timestamp>-<pid>.json
/data/data/<package>/files/pxojdumper/dump-<timestamp>-<pid>.cs
```

- `native_address`: ARM32 Thumb ビットを分離した実行時アドレス。
- `raw_method_pointer`: runtime の MethodInfo から読んだ元のポインター。
- `native_offset`: 所属 ELF の最小 PT_LOAD 仮想アドレスを基準とした RVA。
- `image_base`: その最小 PT_LOAD の実行時アドレス。
- `elf_load_bias`: ローダーが報告する ELF のロードバイアス。
- `elf_virtual_address`: `native_address - elf_load_bias`。
- `elf_file_offset`: 対応する ELF 内のファイル位置。非ファイル領域は `null`。
- `offset_status` / `offset_confidence`: 検証状態と条件付きであることの明示。

アドレス類は精度損失を避けるため16進文字列で保存します。アドレス、RVA、ELF 仮想アドレス、ファイルオフセットは別の値です。ASLRにより実行時アドレスは変わります。詳細は [ネイティブオフセット仕様](docs/NATIVE_OFFSETS.md)。

## 対応範囲と制限

ネイティブ抽出は、Unity 2020.3 系・2022.3 系で確認できる2種類の MethodInfo レイアウトに対応する構造を対象とします。**Unity バージョンを自動判定した結果ではありません。** 名前・宣言クラス・戻り値型のポインター、token、引数数、flags、iflagsを公開APIの返り値と照合します。さらに初期メモリマップと ELF 実行可能セグメントの対応を確認します。

成功時の `layout_and_mapping_snapshot_validated` は、この構造照合と初期マッピング照合が通ったという意味です。`conditional_on_runtime_layout` のとおり、任意の改変runtimeで正しい関数本体であることまで証明しません。共有generic実装やthunkが返る場合があり、複数メソッドが同じアドレスを持つこともあります。マッピングは開始時のスナップショットで、後の再配置・権限変更を完全には追跡しません。

未対応・失敗時は `native_address` / `native_offset` を `null` にし、理由を記録します。例: 不一致レイアウト、補助export不足、読み取り拒否、NULLポインター、実行不能領域、所属ELF不明。

Cocos2d-x、UE4/UE5、Mono、ARM変換環境のブリッジロード、assets復元、暗号解除、保護回避、完全なSDK/ソース復元には対応しません。フィールドのstatic/literal属性によっては、APIの返すoffsetをインスタンス内位置として使えません。

**処理は対象アプリ内で実行されます。** 非互換APIや不安定なruntimeでは、クラッシュ・停止・起動遅延が起きる可能性があります。許可されたテスト環境で使用してください。

収集は20万レコード、レコード間で約60秒、JSONとテキスト合計64MiBを確認します。時間・容量は協調的な制限で、API内の停止を中断せず、1レコード分の容量超過がありえます。部分収集は `partial`、起動・保存エラーは Android logcat の `pxojdumper` タグで確認できます。共有Downloadへ自動コピーしません。

## テスト

```sh
python3 -m unittest discover -s tests -v
node tests/webui_test.mjs
```

ホストテストは模擬IL2CPP runtimeと実際にロードしたテスト用ELFを使用します。すべての環境で動作するかは保証できません。ビルド・検証状況は [TEST_RESULTS.md](TEST_RESULTS.md) に記載しています。

## ライセンス

[0BSD](LICENSE)。公式 Zygisk SDK ヘッダーの原文・著作権・許諾を保持しています。外部コードと技術参照は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。
