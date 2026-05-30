"""Azure Speech：將新聞稿文字轉成 MP3 音檔。"""

import configparser
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.ini"
DEFAULT_VOICE = "zh-TW-HsiaoChenNeural"


def _load_speech_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> speechsdk.SpeechConfig:
    config = configparser.ConfigParser()
    if not config_path.is_file():
        raise FileNotFoundError(
            f"找不到 {config_path}，請複製 config.ini.example 為 config.ini 並填入 Azure Speech 金鑰。"
        )
    config.read(config_path, encoding="utf-8")
    section = config["AzureSpeech"]
    speech_config = speechsdk.SpeechConfig(
        subscription=section["SPEECH_KEY"],
        region=section["SPEECH_REGION"],
    )
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio16Khz64KBitRateMonoMp3
    )
    speech_config.speech_synthesis_voice_name = section.get(
        "VOICE_NAME", DEFAULT_VOICE
    )
    return speech_config


def text_to_speech(text: str, output_path: str | Path) -> Path:
    """
    將新聞稿（字串）合成為 MP3。

    Args:
        text: GPT 產生的新聞稿全文
        output_path: 輸出檔案路徑（例如 static/resource/summary.mp3）

    Returns:
        寫入完成的音檔路徑
    """
    if not text or not text.strip():
        raise ValueError("新聞稿內容不可為空")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    speech_config = _load_speech_config()
    audio_config = speechsdk.audio.AudioOutputConfig(filename=str(output_path))
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=audio_config
    )

    result = synthesizer.speak_text_async(text.strip()).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return output_path

    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        message = details.error_details or str(details.reason)
        raise RuntimeError(f"語音合成失敗: {message}")

    raise RuntimeError(f"語音合成失敗: {result.reason}")
