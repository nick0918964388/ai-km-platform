/**
 * useVoiceInput Hook
 * Manages VAD (Voice Activity Detection) for voice input functionality
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { MicVAD } from '@ricky0123/vad-web';
import { transcribe } from '@/services/asr';

type VoiceInputState = 'idle' | 'recording' | 'processing';

interface UseVoiceInputOptions {
  onTranscriptionReceived?: (text: string) => void;
  onError?: (error: Error) => void;
}

interface UseVoiceInputReturn {
  state: VoiceInputState;
  error: string | null;
  startListening: () => Promise<void>;
  stopListening: () => void;
  isRecording: boolean;
  isProcessing: boolean;
}

export function useVoiceInput({
  onTranscriptionReceived,
  onError,
}: UseVoiceInputOptions = {}): UseVoiceInputReturn {
  const [state, setState] = useState<VoiceInputState>('idle');
  const [error, setError] = useState<string | null>(null);
  const vadRef = useRef<MicVAD | null>(null);
  const isStartingRef = useRef(false);

  const handleSpeechEnd = useCallback(
    async (audio: Float32Array) => {
      setState('processing');
      setError(null);

      try {
        // Convert Float32Array to WAV blob
        const audioBlob = await convertToWavBlob(audio);

        // Send to ASR API
        const text = await transcribe(audioBlob);

        if (text && text.trim()) {
          onTranscriptionReceived?.(text);
        }

        // Return to recording state if still active
        if (vadRef.current) {
          setState('recording');
        } else {
          setState('idle');
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Transcription failed';
        setError(errorMessage);
        onError?.(err instanceof Error ? err : new Error(errorMessage));

        // Return to recording state to allow retry
        if (vadRef.current) {
          setState('recording');
        } else {
          setState('idle');
        }
      }
    },
    [onTranscriptionReceived, onError]
  );

  const startListening = useCallback(async () => {
    if (isStartingRef.current || vadRef.current) {
      return;
    }

    isStartingRef.current = true;
    setError(null);

    try {
      // Request microphone permission
      await navigator.mediaDevices.getUserMedia({ audio: true });

      // Initialize VAD
      const vad = await MicVAD.new({
        onSpeechEnd: handleSpeechEnd,
      });

      vadRef.current = vad;
      vad.start();
      setState('recording');
    } catch (err) {
      const errorMessage =
        err instanceof Error && err.name === 'NotAllowedError'
          ? 'Microphone permission denied'
          : 'Failed to start voice input';

      setError(errorMessage);
      onError?.(new Error(errorMessage));
      setState('idle');
    } finally {
      isStartingRef.current = false;
    }
  }, [handleSpeechEnd, onError]);

  const stopListening = useCallback(() => {
    if (vadRef.current) {
      vadRef.current.pause();
      vadRef.current = null;
      setState('idle');
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (vadRef.current) {
        vadRef.current.pause();
        vadRef.current = null;
      }
    };
  }, []);

  return {
    state,
    error,
    startListening,
    stopListening,
    isRecording: state === 'recording',
    isProcessing: state === 'processing',
  };
}

/**
 * Convert Float32Array audio data to WAV blob
 * VAD provides Float32Array, but ASR API expects WAV format
 */
async function convertToWavBlob(audioData: Float32Array): Promise<Blob> {
  const sampleRate = 16000; // VAD default sample rate
  const numChannels = 1; // Mono
  const bitsPerSample = 16;

  // Convert Float32Array to Int16Array
  const int16Data = new Int16Array(audioData.length);
  for (let i = 0; i < audioData.length; i++) {
    const sample = Math.max(-1, Math.min(1, audioData[i]));
    int16Data[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }

  // Create WAV header
  const wavHeader = new ArrayBuffer(44);
  const view = new DataView(wavHeader);

  // "RIFF" chunk descriptor
  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + int16Data.length * 2, true);
  writeString(view, 8, 'WAVE');

  // "fmt " sub-chunk
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true); // Subchunk1Size (PCM)
  view.setUint16(20, 1, true); // AudioFormat (PCM)
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * (bitsPerSample / 8), true); // ByteRate
  view.setUint16(32, numChannels * (bitsPerSample / 8), true); // BlockAlign
  view.setUint16(34, bitsPerSample, true);

  // "data" sub-chunk
  writeString(view, 36, 'data');
  view.setUint32(40, int16Data.length * 2, true);

  // Combine header and audio data
  const wavBlob = new Blob([wavHeader, int16Data], { type: 'audio/wav' });
  return wavBlob;
}

function writeString(view: DataView, offset: number, string: string): void {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}
