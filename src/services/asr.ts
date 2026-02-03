/**
 * ASR (Automatic Speech Recognition) Service
 * Handles transcription of audio to text using the ASR API
 */

const ASR_API_URL = process.env.NEXT_PUBLIC_ASR_API_URL || 'https://voicemodel.nickai.cc';

interface TranscriptionResponse {
  text: string;
}

/**
 * Transcribe audio blob to text using ASR API
 * @param audioBlob - Audio blob to transcribe (usually from VAD)
 * @returns Transcribed text
 * @throws Error if transcription fails
 */
export async function transcribe(audioBlob: Blob): Promise<string> {
  try {
    const formData = new FormData();
    formData.append('file', audioBlob, 'audio.wav');

    const response = await fetch(`${ASR_API_URL}/v1/audio/transcriptions`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`ASR API error: ${response.status} ${response.statusText}`);
    }

    const data: TranscriptionResponse = await response.json();
    return data.text;
  } catch (error) {
    console.error('Transcription error:', error);
    throw new Error(
      error instanceof Error ? error.message : 'Failed to transcribe audio'
    );
  }
}
