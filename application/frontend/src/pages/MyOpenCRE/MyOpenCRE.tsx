import './MyOpenCRE.scss';

import React, { useState } from 'react';
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

  /* ------------------ CSV DOWNLOAD ------------------ */

  const downloadCreCsv = async () => {
    try {
      const response = await fetch(`${apiUrl}/cre_csv`, {
        method: 'GET',
        headers: { Accept: 'text/csv' },
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);

      const link = document.createElement('a');
      link.href = url;
      link.download = 'opencre-cre-mapping.csv';
      document.body.appendChild(link);
      link.click();

      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('CSV download failed:', err);
      alert('Failed to download CRE CSV');
    }
  };

  /* ------------------ FILE SELECTION ------------------ */

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setSuccess(null);

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
  };

  /* ------------------ CSV UPLOAD ------------------ */

  const uploadCsv = async () => {
    if (!selectedFile) return;

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
        return;
      }

      setSuccess(payload);
      setSelectedFile(null);
    } catch (err: any) {
      setError({
        success: false,
        type: 'CLIENT_ERROR',
        message: err.message || 'Unexpected error during import',
      });
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

  /* ------------------ UI ------------------ */

  return (
    <Container style={{ marginTop: '3rem' }}>
      <Header as="h1">MyOpenCRE</Header>

      <p>
        MyOpenCRE allows you to map your own security standard (e.g. SOC2) to OpenCRE Common Requirements
        using a CSV spreadsheet.
      </p>

      <p>
        Start by downloading the CRE catalogue below, then map your standard’s controls or sections to CRE IDs
        in the spreadsheet.
      </p>

      <div className="myopencre-section">
        <Button primary onClick={downloadCreCsv}>
          Download CRE Catalogue (CSV)
        </Button>
      </div>

      <div className="myopencre-section myopencre-upload">
        <Header as="h3">Upload Mapping CSV</Header>

        <p>Upload your completed mapping spreadsheet to import your standard into OpenCRE.</p>

        {!isUploadEnabled && (
          <Message info className="myopencre-disabled">
            CSV upload is disabled on hosted environments due to resource constraints.
            <br />
            Please run OpenCRE locally to enable standard imports.
          </Message>
        )}

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

        <Form>
          <Form.Field>
            <input type="file" accept=".csv" disabled={!isUploadEnabled || loading} onChange={onFileChange} />
          </Form.Field>

          <Button
            primary
            loading={loading}
            disabled={!isUploadEnabled || !selectedFile || loading}
            onClick={uploadCsv}
          >
            Upload CSV
          </Button>
        </Form>
      </div>
    </Container>
  );
};
