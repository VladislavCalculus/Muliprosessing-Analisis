"""Read WAV files and pass validated audio to the signal-processing stage."""

from .reader import WavFile, WavSource, read_wav, read_wav_batch, read_wav_details

__all__ = ["WavFile", "WavSource", "read_wav", "read_wav_batch", "read_wav_details"]
