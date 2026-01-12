import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import tempfile
import os

class AudioRecorder:
    def __init__(self, fs=44100, channels=1):
        self.fs = fs
        self.channels = channels
        self.recording = []
        self.stream = None

    def list_devices(self):
        """Returns a filtered list of unique input devices (id, name)."""
        devices = sd.query_devices()
        input_devices = []
        seen_names = set()
        
        # Common system-generated names to ignore (English/French/Generic)
        ignored_names = [
            "Microsoft Sound Mapper", "Mappeur de sons Microsoft",
            "Primary Sound Capture Driver", "Pilote de capture audio principal",
            "Stereo Mix", "Mixage stéréo"
        ]

        for i, dev in enumerate(devices):
            name = dev['name']
            if dev['max_input_channels'] > 0:
                # 1. Ignore specific Windows system wrappers
                is_ignored = False
                for ignored in ignored_names:
                    if name.startswith(ignored):
                        is_ignored = True
                        break
                if is_ignored:
                    continue
                
                # 2. Deduplicate names (keep first occurrence)
                if name not in seen_names:
                    input_devices.append((i, name))
                    seen_names.add(name)
        
        return input_devices

    def start(self, device_index=None):
        """Starts recording audio from the specified or default microphone."""
        self.recording = [] # Reset recording
        try:
            self.stream = sd.InputStream(
                device=device_index,
                samplerate=self.fs, 
                channels=self.channels, 
                callback=self._callback
            )
            self.stream.start()
            print(f"Enregistrement démarré (Device ID: {device_index})...")
        except Exception as e:
            print(f"[ERROR] Impossible de démarrer l'enregistrement sur le device {device_index}: {e}")
            # Fallback to default if specific fails
            if device_index is not None:
                print("Tentative avec le périphérique par défaut...")
                self.start(device_index=None)

    def stop(self) -> str:
        """Stops recording and saves to a temporary WAV file. Returns the file path."""
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        
        print("Enregistrement terminé.")
        
        if not self.recording:
            return None

        # Concatenate all blocks
        myrecording = np.concatenate(self.recording, axis=0)
        
        # Convert to int16 to ensure standard PCM WAV format (more compatible)
        myrecording = (myrecording * 32767).astype(np.int16)
        
        # Create a temp file
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        
        # Save WAV
        wav.write(path, self.fs, myrecording)
        return path

    def _callback(self, indata, frames, time, status):
        """Callback for sounddevice."""
        if status:
            print(status)
        self.recording.append(indata.copy())
