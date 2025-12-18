import React, { useState } from 'react';
import { Button, Container, Form, Header, Message } from 'semantic-ui-react';

import { useEnvironment } from '../../hooks';

export const MyOpenCRE = () => {
  const { apiUrl } = useEnvironment();

<<<<<<< Updated upstream
  const downloadCreCsv = async () => {
    try {
      const baseUrl = apiUrl || window.location.origin;
      const backendUrl = baseUrl.includes('localhost') ? 'http://127.0.0.1:5000' : baseUrl;

      const response = await fetch(`${backendUrl}/cre_csv`, {
        method: 'GET',
        headers: {
          Accept: 'text/csv',
        },
=======
  /**
   * Upload is enabled only in local/dev environments.
   * In prod, apiUrl === '/rest/v1'
   */
  const isUploadEnabled = apiUrl !== '/rest/v1';

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<any | null>(null);

  /* ------------------ CSV DOWNLOAD ------------------ */

  const downloadCreCsv = async () => {
    try {
      const response = await fetch(`${apiUrl}/cre_csv`, {
        method: 'GET',
        headers: { Accept: 'text/csv' },
>>>>>>> Stashed changes
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

<<<<<<< Updated upstream
  // Upload enabled locally, disabled on hosted OpenCRE (Heroku)
  const isUploadEnabled = !apiUrl.includes('opencre.org');

  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
=======
  /* ------------------ FILE SELECTION ------------------ */

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setSuccess(null);

>>>>>>> Stashed changes
    if (!e.target.files || e.target.files.length === 0) return;

    const file = e.target.files[0];

<<<<<<< Updated upstream
    // Client-side CSV validation
    if (!file.name.toLowerCase().endsWith('.csv')) {
      alert('Please upload a valid CSV file.');
=======
    // Enforce CSV only
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please upload a valid CSV file.');
>>>>>>> Stashed changes
      e.target.value = '';
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

<<<<<<< Updated upstream
=======
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

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || 'CSV import failed');
      }

      const result = await response.json();
      setSuccess(result);
      setSelectedFile(null);
    } catch (err: any) {
      setError(err.message || 'Unexpected error during import');
    } finally {
      setLoading(false);
    }
  };

  /* ------------------ UI ------------------ */

>>>>>>> Stashed changes
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

      <Button primary onClick={downloadCreCsv}>
        Download CRE Catalogue (CSV)
      </Button>

      <Header as="h3" style={{ marginTop: '2rem' }}>
        Upload Mapping CSV
      </Header>

      <p>Upload your completed mapping spreadsheet to import your standard into OpenCRE.</p>

      {!isUploadEnabled && (
        <Message info>
          CSV upload is disabled on hosted environments due to resource constraints.
          <br />
          Please run OpenCRE locally to enable standard imports.
        </Message>
      )}

<<<<<<< Updated upstream
      <Form>
        <Form.Field>
          <input type="file" accept=".csv" disabled={!isUploadEnabled} onChange={onFileChange} />
=======
      {error && <Message negative>{error}</Message>}

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
>>>>>>> Stashed changes
        </Form.Field>

        <Button
          primary
<<<<<<< Updated upstream
          disabled={!isUploadEnabled || !selectedFile}
          onClick={() => alert('CSV import will be implemented in a follow-up PR.')}
=======
          loading={loading}
          disabled={!isUploadEnabled || !selectedFile || loading}
          onClick={uploadCsv}
>>>>>>> Stashed changes
        >
          Upload CSV
        </Button>
      </Form>
    </Container>
  );
};
