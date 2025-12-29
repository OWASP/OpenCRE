import './MyOpenCRE.scss';

import React, { useRef, useState } from 'react';
import { Button, Container, Form, Header, Message } from 'semantic-ui-react';

import { useEnvironment } from '../../hooks';

type RowValidationError = {
  row: number;
  code: string;
  message: string;
  column?: string;
};

type ImportErrorResponse = {
  success: false;
  type: string;
  message?: string;
  errors?: RowValidationError[];
};

export const MyOpenCRE = () => {
  const { apiUrl } = useEnvironment();
  const isUploadEnabled = apiUrl !== '/rest/v1';

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ImportErrorResponse | null>(null);
  const [success, setSuccess] = useState<any | null>(null);

  const [preview, setPreview] = useState<{
    rows: number;
    creMappings: number;
    uniqueSections: number;
    creColumns: string[];
  } | null>(null);

  const [info, setInfo] = useState<string | null>(null);
  const [confirmedImport, setConfirmedImport] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  /* ------------------ FILE SELECTION ------------------ */

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setSuccess(null);
    setInfo(null);
    setConfirmedImport(false);
    setPreview(null);

    if (!e.target.files || e.target.files.length === 0) return;

    const file = e.target.files[0];

    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError({
        success: false,
        type: 'FILE_ERROR',
        message: 'Please upload a valid CSV file.',
      });
      e.target.value = '';
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
    generateCsvPreview(file);
  };
  /* ------------------ CSV DOWNLOAD ------------------ */

  const downloadTemplate = () => {
    const headers = ['standard_name', 'standard_section', 'cre_id', 'notes'];

    const csvContent = headers.join(',') + '\n';

    const blob = new Blob([csvContent], {
      type: 'text/csv;charset=utf-8;',
    });

    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.setAttribute('download', 'myopencre_mapping_template.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };
  /* ------------------ CSV UPLOAD ------------------ */

  const uploadCsv = async () => {
    if (!selectedFile || !confirmedImport) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    const formData = new FormData();
    formData.append('cre_csv', selectedFile);

    try {
      const response = await fetch(`${apiUrl}/cre_csv_import`, {
        method: 'POST',
        body: formData,
      });

      if (response.status === 403) {
        throw new Error(
          'CSV import is disabled on hosted environments. Run OpenCRE locally with CRE_ALLOW_IMPORT=true.'
        );
      }

      const payload = await response.json();

      if (!response.ok) {
        setError(payload);
        setPreview(null);
        setConfirmedImport(false);
        return;
      }

      if (payload.import_type === 'noop') {
        setInfo(
          'Import completed successfully, but no new CREs or standards were added because all mappings already exist.'
        );
      } else {
        setSuccess(payload);
      }

      setConfirmedImport(false);
      setPreview(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (err: any) {
      setError({
        success: false,
        type: 'CLIENT_ERROR',
        message: err.message || 'Unexpected error during import',
      });
      setPreview(null);
      setConfirmedImport(false);
    } finally {
      setLoading(false);
    }
  };

  /* ------------------ ERROR RENDERING ------------------ */

  const renderErrorMessage = () => {
    if (!error) return null;

    if (error.errors && error.errors.length > 0) {
      return (
        <Message negative>
          <strong>Import failed due to validation errors</strong>
          <ul>
            {error.errors.map((e, idx) => (
              <li key={idx}>
                <strong>Row {e.row}:</strong> {e.message}
              </li>
            ))}
          </ul>
        </Message>
      );
    }

    return <Message negative>{error.message || 'Import failed'}</Message>;
  };

  /* ------------------ CSV PREVIEW ------------------ */

  const generateCsvPreview = async (file: File) => {
    const text = await file.text();
    const lines = text.split('\n').filter(Boolean);

    if (lines.length < 2) {
      setPreview(null);
      return;
    }

    const headers = lines[0].split(',').map((h) => h.trim());
    const rows = lines.slice(1);

    const creColumns = headers.filter((h) => h.startsWith('CRE'));
    let creMappings = 0;
    const sectionSet = new Set<string>();

    rows.forEach((line) => {
      const values = line.split(',');
      const rowObj: Record<string, string> = {};

      headers.forEach((h, i) => {
        rowObj[h] = (values[i] || '').trim();
      });

      const name = (rowObj['standard|name'] || '').trim();
      const id = (rowObj['standard|id'] || '').trim();

      if (name || id) {
        sectionSet.add(`${name}|${id}`);
      }

      creColumns.forEach((col) => {
        if (rowObj[col]) creMappings += 1;
      });
    });

    setPreview({
      rows: rows.length,
      creMappings,
      uniqueSections: sectionSet.size,
      creColumns,
    });
  };

  /* ------------------ UI ------------------ */

  return (
    <Container className="myopencre-container">
      <Header as="h1">MyOpenCRE</Header>

      <div className="myopencre-section">
        <Button primary onClick={downloadCreCsv}>
          Download CRE Catalogue (CSV)
        </Button>
      </div>

      <div className="myopencre-section myopencre-upload">
        <Header as="h3">Upload Mapping CSV</Header>

        {renderErrorMessage()}

        {success && (
          <Message positive>
            <strong>Import successful</strong>
            <ul>
              <li>New CREs added: {success.new_cres?.length ?? 0}</li>
              <li>Standards imported: {success.new_standards}</li>
            </ul>
          </Message>
        )}

        {confirmedImport && !loading && !success && !error && (
          <Message positive>
            CSV validated successfully. Click <strong>Upload CSV</strong> to start importing.
          </Message>
        )}

        {preview && (
          <Message info className="myopencre-preview">
            <strong>Import Preview</strong>
            <ul>
              <li>Rows detected: {preview.rows}</li>
              <li>CRE mappings found: {preview.creMappings}</li>
              <li>Unique standard sections: {preview.uniqueSections}</li>
              <li>CRE columns detected: {preview.creColumns.join(', ')}</li>
            </ul>

            <Button
              primary
              size="small"
              onClick={() => {
                setPreview(null);
                setConfirmedImport(true);
              }}
            >
              Confirm Import
            </Button>

            <Button
              size="small"
              onClick={() => {
                setPreview(null);
                setConfirmedImport(false);
                setSelectedFile(null);
                if (fileInputRef.current) fileInputRef.current.value = '';
              }}
            >
              Cancel
            </Button>
          </Message>
        )}

        <Form>
          <Form.Field>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              disabled={!isUploadEnabled || loading || !!preview}
              onChange={onFileChange}
            />
          </Form.Field>

          <Button
            primary
            loading={loading}
            disabled={!isUploadEnabled || !selectedFile || !confirmedImport || loading}
            onClick={uploadCsv}
          >
            Upload CSV
          </Button>
        </Form>
      </div>
    </Container>
  );
};
