# Wuthering Waves MIDI Player

Standard MIDI File（SMF）のNote OnイベントをWindowsのキーボード入力へ変換し、
鳴潮の琴を自動演奏するツールです。

MIDI音源、DAW、仮想MIDIポートは再生時には必要ありません。

## 動作環境

- Windows 10 / 11
- Python 3.10以降
- 鳴潮の琴が演奏できる状態

## セットアップ

PowerShellでプロジェクトディレクトリを開き、仮想環境を作成します。
外部パッケージは使用していません。

```powershell
python -m venv .venv
```

## 起動

鳴潮は管理者権限で動作することがあります。通常権限のアプリから管理者権限のゲームへは
Windowsがキー入力を遮断するため、通常は次のランチャーを使用してください。

```text
run_player_admin.cmd
```

ファイルをダブルクリックし、ユーザーアカウント制御（UAC）を許可します。GUIタイトルに
`[Administrator]`と表示されていれば、管理者権限で起動しています。

鳴潮が通常権限で動いている環境では、次のコマンドでも起動できます。

```powershell
.\.venv\Scripts\pythonw.exe .\run_player.pyw
```

## 使い方

1. `Open...`でMIDIファイルを選択します。
2. 検証結果とクオンタイズ対象を確認します。
3. `Play`またはF6を押します。
4. 3秒の待機中に、鳴潮の琴画面へフォーカスを移します。
5. F7またはEscで停止します。

停止、エラー、アプリ終了時には、ツールが押下中として管理しているキーをすべて解放します。

## 対応MIDI

- SMF Type 0 / Type 1
- PPQベースのタイミング
- Set Tempoメタイベント
- 複数トラックの統合
- Running Status
- Note On（Velocity 0はNote Offとして無視）

SMPTEタイムコード形式とリアルタイムMIDI入力には対応していません。MIDIのノート長とVelocityは
演奏結果に使用せず、すべて固定長のキー入力へ変換します。

## 設定

[keymap.json](keymap.json)でキー配置と再生動作を変更できます。

| 設定 | 内容 |
|---|---|
| `pulse_ms` | キーを押している時間（ミリ秒） |
| `start_delay_ms` | 再生開始までの待機時間（ミリ秒） |
| `unmapped_note` | 未割当ノートの処理方法 |
| `require_target_window` | 再生開始時に前面ウィンドウを確認するか |
| `target_window_title` | 対象ウィンドウ名に含まれる文字列 |
| `keymap` | MIDIノート番号からキーボードキーへの対応 |

`unmapped_note`では次の値を指定できます。

- `error`: 未割当ノートがあれば再生しない
- `ignore`: 未割当ノートを無視する
- `quantize`: 音域外をオクターブ移動し、黒鍵を最寄りの割当済み音へ寄せる

同じ距離に候補がある場合、`quantize`は低い音を選択します。

## MIDIの検証

キー入力を送信せずにMIDIを検証できます。

```powershell
.\.venv\Scripts\python.exe .\inspect_midi.py ".\midi\example.mid"
```

SMF形式、PPQ、演奏時間、Note On数、最大同時発音数、テンポイベント数、未割当ノートを表示します。
終了コード0は再生可能、2は`error`モードで未割当ノートが存在することを示します。

## テスト

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## ログ

再生エラーと最大スケジューリング遅延は`wuthering-midi-player.log`へ記録されます。

## MIDIファイルについて

`midi/`はGit管理対象外です。楽曲データの著作権と利用条件を確認し、各自で用意してください。
