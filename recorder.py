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

    def start(self):
        """Starts recording audio from the default microphone."""
        self.recording = [] # Reset recording
        self.stream = sd.InputStream(samplerate=self.fs, channels=self.channels, callback=self._callback)
        self.stream.start()
        print("Enregistrement démarré...")

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
