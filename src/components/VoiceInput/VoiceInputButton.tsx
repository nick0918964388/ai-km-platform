/**
 * VoiceInputButton Component
 * Microphone button with visual feedback for voice input states
 */

'use client';

import React from 'react';
import { Microphone, StopFilled } from '@carbon/icons-react';
import { IconButton } from '@carbon/react';
import { useVoiceInput } from './useVoiceInput';

interface VoiceInputButtonProps {
  onTranscriptionReceived: (text: string) => void;
  className?: string;
}

export function VoiceInputButton({
  onTranscriptionReceived,
  className = '',
}: VoiceInputButtonProps) {
  const { state, error, startListening, stopListening, isRecording, isProcessing } =
    useVoiceInput({
      onTranscriptionReceived,
      onError: (err) => {
        console.error('Voice input error:', err);
      },
    });

  const handleClick = () => {
    if (isRecording || isProcessing) {
      stopListening();
    } else {
      startListening();
    }
  };

  const getTooltipText = () => {
    if (error) {
      return error;
    }
    if (isProcessing) {
      return '處理中...';
    }
    if (isRecording) {
      return '停止錄音';
    }
    return '語音輸入';
  };

  return (
    <div className={`voice-input-button-wrapper ${className}`}>
      <IconButton
        kind="ghost"
        size="md"
        label={getTooltipText()}
        onClick={handleClick}
        disabled={state === 'processing'}
        className={isRecording || isProcessing ? 'text-red-600' : ''}
      >
        {isRecording || isProcessing ? <StopFilled size={20} /> : <Microphone size={20} />}
      </IconButton>

      {/* Recording indicator - pulsing red dot */}
      {isRecording && (
        <div className="recording-indicator">
          <div className="pulse-dot" />
        </div>
      )}

      {/* Processing spinner */}
      {isProcessing && (
        <div className="processing-indicator">
          <div className="spinner" />
        </div>
      )}

      <style jsx>{`
        .voice-input-button-wrapper {
          position: relative;
          display: inline-block;
        }

        .voice-input-button {
          position: relative;
        }

        .recording-indicator,
        .processing-indicator {
          position: absolute;
          top: -4px;
          right: -4px;
          pointer-events: none;
        }

        .pulse-dot {
          width: 12px;
          height: 12px;
          background-color: #da1e28;
          border-radius: 50%;
          animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
          0% {
            opacity: 1;
            transform: scale(1);
          }
          50% {
            opacity: 0.6;
            transform: scale(1.2);
          }
          100% {
            opacity: 1;
            transform: scale(1);
          }
        }

        .spinner {
          width: 12px;
          height: 12px;
          border: 2px solid #f4f4f4;
          border-top-color: #da1e28;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }
      `}</style>
    </div>
  );
}
