# myds

Macのカメラで顔を追跡し、指向性スピーカーを載せた2軸サーボ（Pan・Tilt）の角度を制御するmacOSアプリ

Claude Codeを使用して開発

## アプリのビルドとインストール

```sh
./scripts/build.sh
```

- 成果物は `dist/myds.app`
- ビルド専用の仮想環境 `.build-venv` を自動で作成する。アプリは仮想環境に依存しない
- 別のPythonを使う場合は `PYTHON=python3.12 ./scripts/build.sh`

インストール
1. `dist/myds.app` を「アプリケーション」フォルダへコピーする
2. Spotlightで「myds」と検索するか、Finderからダブルクリックで起動する
3. 初回は「myds がカメラへのアクセスを求めています」と出るので「許可」を押す
4. Dockに残す場合は、起動中のアイコンを右クリック >「オプション」>「Dockに追加」

注意
- 署名がアドホックのため、再ビルドしてコピーし直すたびにカメラ許可を再度求められる
- 毎回の確認を避けたい場合は、キーチェーンアクセスでコード署名用の自己署名証明書を作り、その名前を指定してビルドする
  - `MYDS_SIGN_IDENTITY="証明書名" ./scripts/build.sh`
- カメラを拒否してしまった場合は「システム設定 > プライバシーとセキュリティ > カメラ」で myds をONにして再起動する
  - 一覧にない場合は `tccutil reset Camera io.github.sendarionn.myds` を実行して再起動する
- 初回起動時のみ、MediaPipeが使うフォントキャッシュの作成で15秒ほどかかる（`~/Library/Caches/myds` に保存）
- 終了するとカメラとシリアル接続を解放する

## 開発時の起動

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

- Python 3.11以降
- 顔検出モデル `models/blaze_face_short_range.tflite` を同梱（MediaPipe, Apache 2.0）
- カメラ許可は起動したターミナル（Terminal.app、VS Codeなど）に付与される
  - 許可されていない場合は「システム設定 > プライバシーとセキュリティ > カメラ」で該当アプリを許可する
  - 許可後は3秒以内に自動で再接続される

## 画面

- 左: カメラ映像、顔検出枠、顔中心座標
- 右上: 仮想スピーカーの上面図（Pan）と側面図（Tilt）
  - 橙の破線が目標角度、青が回転速度を反映した現在角度
  - 灰色の太い円弧が設定した可動範囲
- 下部: 追従状態、出力先、fps、顔方向の角度

## 操作

操作タブ
- 自動追従: ONで最も大きい顔を追従する
  - 顔が「顔ロスト判定」の時間検出されないと追従を止め、角度を保持する
  - 顔を再検出すると追従を再開する
- 一時停止: 自動追従を維持したまま角度の更新を止める
- 中央へ: 自動追従をOFFにして 90°・90° へ移動する
- 緊急停止: その場で停止し、シリアル送信も止める
  - 解除後は手動モードになり、現在角度から操作を再開する
- Pan・Tiltスライダー: 自動追従OFF時のみ操作できる

設定タブ
- カメラ、検出信頼度、デッドゾーン、平滑化、最大回転速度、角度更新頻度、顔ロスト判定時間
- 水平・垂直画角: 角度計算に使う。カメラに合わせて調整する
- Pan・Tiltの最小・最大角度、回転方向の反転

出力タブ
1. 出力を「Serial」に切り替える
2. ポートを選び「接続」を押す（確認ダイアログが出る）
3. 接続直後は送信しない。「送信開始」を押すと送信を始める
- 「角度指示」には送信する内容が常に表示されるため、実機なしでも確認できる
- 送信エラー時は自動で切断する。カメラエラー時と緊急停止時は送信を止める
- Simulationに戻すと切断する

## 通信プロトコル

- 115200bps、改行 `\n` 区切りのテキスト
- `P=95,T=82`（Pan・Tiltの角度、単位は度、整数）
- 仮想サーボの現在角度（回転速度制限後）を、角度更新頻度ごとに値が変わった時だけ送る
- Arduino用の受信スケッチ: `firmware/servo_receiver/servo_receiver.ino`
  - 最初の指示を受け取るまでサーボを動かさない

## 構成

| ファイル | 役割 |
| --- | --- |
| `speaker_tracker/camera.py` | カメラ取得と検出を別スレッドで実行 |
| `speaker_tracker/detector.py` | MediaPipe Face Detector |
| `speaker_tracker/controller.py` | 角度計算（ピンホールモデル）、平滑化、デッドゾーン、状態管理 |
| `speaker_tracker/simulation.py` | 仮想サーボ（最大回転速度の制限） |
| `speaker_tracker/serial_controller.py` | PySerialによる送信 |
| `speaker_tracker/ui.py` | GUI |
| `main.py` | 起動 |
| `myds.spec` | PyInstallerのビルド設定 |
| `scripts/build.sh` | アプリのビルド |

カメラとスピーカーの位置差は `TrackingSettings.speaker_offset_m` で補正できる構造にしてある（顔幅から距離を推定）
既定値は0で、補正は行わない
