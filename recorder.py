"""
Microphone audio recorder for Dictating-app.

Records 44.1 kHz 16-bit mono PCM WAV audio using `sounddevice` and `scipy.io.wavfile`,
and enumerates physical MME input devices for the system tray microphone selector.
"""

import logging
import os
import wave
from typing import Dict, List, Optional

import numpy as np

try:
    from scipy.io.wavfile import write as scipy_wav_write
except ImportError:
    scipy_wav_write = None  # type: ignore

logger = logging.getLogger("dictating_app")

try:
    import sounddevice as sd
except Exception:
    sd = None  # type: ignore


class AudioRecorder:
    """Streams microphone input into a local WAV file."""

    def __init__(
        self,
        filename: str = "temp_recording.wav",
        sample_rate: int = 44100,
    ) -> None:
        """Initialize the audio recorder.

        Args:
            filename: Output WAV filename for recorded audio.
            sample_rate: Audio sampling rate in Hz (default 44100).
        """
        self.filename = filename
        self.sample_rate = sample_rate
        self.recording: bool = False
        self.audio_data: List[np.ndarray] = []
        self.stream = None
        self.device_index: Optional[int] = None

    @staticmethod
    def get_input_devices() -> Dict[int, str]:
        """Return a mapping of `{device_index: device_name}` for MME input devices."""
        devices_dict: Dict[int, str] = {}
        if sd is None:
            return devices_dict
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()

            mme_index = 0
            for idx, api in enumerate(hostapis):
                if "MME" in api.get("name", ""):
                    mme_index = idx
                    break

            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0 and dev.get("hostapi") == mme_index:
                    name = dev.get("name", f"Device {idx}")
                    if "Mappeur de sons" not in name and "Sound Mapper" not in name:
                        devices_dict[idx] = name
        except Exception as exc:
            logger.warning("Error querying audio input devices: %s", exc)
        return devices_dict

    def set_device(self, index: int) -> None:
        """Select the active microphone device index."""
        self.device_index = index
        logger.info("AudioRecorder device set to index=%s", index)

    def _callback(self, indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        """Sounddevice stream callback accumulating recorded audio frames."""
        if status:
            logger.debug("AudioStream status: %s", status)
        if self.recording:
            self.audio_data.append(indata.copy())

    def start_recording(self) -> None:
        """Begin capturing audio from the selected microphone."""
        if self.recording or sd is None:
            return
        self.recording = True
        self.audio_data = []
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            device=self.device_index,
            callback=self._callback,
        )
        self.stream.start()
        logger.info(
            "Started audio recording (sample_rate=%d, device=%s)",
            self.sample_rate,
            self.device_index,
        )

    def stop_recording(self) -> Optional[str]:
        """Stop capturing audio and write the buffered frames to a WAV file.

        Returns:
            Absolute path to the written WAV file, or `None` if no audio was recorded.
        """
        if not self.recording:
            return None
        self.recording = False
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if not self.audio_data:
            logger.warning("No audio frames captured during recording.")
            return None

        audio_concatenated = np.concatenate(self.audio_data, axis=0)
        abs_path = os.path.abspath(self.filename)
        if scipy_wav_write is not None:
            scipy_wav_write(abs_path, self.sample_rate, audio_concatenated)
        else:
            with wave.open(abs_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_concatenated.astype(np.int16).tobytes())
        duration_sec = len(audio_concatenated) / float(self.sample_rate)
        logger.info(
            "Stopped recording -> saved %s (duration=%.2fs, bytes=%d)",
            abs_path,
            duration_sec,
            os.path.getsize(abs_path),
        )
        return abs_path
