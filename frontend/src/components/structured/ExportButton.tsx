'use client';

import React, { useState } from 'react';
import { Button, Loading } from '@carbon/react';
import { Download, DocumentExport } from '@carbon/icons-react';
import { API_URL, API_KEY, TIMEOUTS, fetchWithTimeout, getErrorMessage } from '@/lib/api';

interface ExportButtonProps {
  exportUrl: string;
  filename?: string;
  label?: string;
  kind?: 'primary' | 'secondary' | 'tertiary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
}

const API_BASE = API_URL;

export default function ExportButton({
  exportUrl,
  filename,
  label = '匯出 CSV',
  kind = 'tertiary',
  size = 'sm',
  disabled = false,
}: ExportButtonProps) {
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async () => {
    setIsExporting(true);
    
    try {
      const response = await fetchWithTimeout(`${API_BASE}${exportUrl}`, {
        headers: API_KEY ? { 'X-API-Key': API_KEY } : {},
        timeout: TIMEOUTS.EXPORT,
      });
      
      if (!response.ok) {
        throw new Error('Export failed');
      }
      
      // Get filename from Content-Disposition header or use provided/default
      const contentDisposition = response.headers.get('Content-Disposition');
      let downloadFilename = filename || 'export.csv';
      
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^";\n]+)"?/);
        if (match) {
          downloadFilename = match[1];
        }
      }
      
      // Create blob and trigger download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = downloadFilename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
    } catch (error) {
      console.error('Export error:', error);
      alert(getErrorMessage(error));
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <Button
      kind={kind}
      size={size}
      disabled={disabled || isExporting}
      renderIcon={isExporting ? undefined : Download}
      onClick={handleExport}
    >
      {isExporting ? (
        <>
          <Loading withOverlay={false} small />
          匯出中...
        </>
      ) : (
        label
      )}
    </Button>
  );
}
