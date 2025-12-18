import React, { useState } from 'react';
import { Button, Container, Form, Header, Message } from 'semantic-ui-react';

import { useEnvironment } from '../../hooks';

export const MyOpenCRE = () => {
  const { apiUrl } = useEnvironment();

  const downloadCreCsv = async () => {
    try {
      const baseUrl = apiUrl || window.location.origin;
      const backendUrl = baseUrl.includes('localhost') ? 'http://127.0.0.1:5000' : baseUrl;

      const response = await fetch(`${backendUrl}/cre_csv`, {
        method: 'GET',
        headers: {
          Accept: 'text/csv',
        },
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

  // Upload enabled locally, disabled on hosted OpenCRE (Heroku)
  const isUploadEnabled = !apiUrl.includes('opencre.org');

  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;

    const file = e.target.files[0];

    // Client-side CSV validation
    if (!file.name.toLowerCase().endsWith('.csv')) {
      alert('Please upload a valid CSV file.');
      e.target.value = '';
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

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

      <Form>
        <Form.Field>
          <input type="file" accept=".csv" disabled={!isUploadEnabled} onChange={onFileChange} />
        </Form.Field>

        <Button
          primary
          disabled={!isUploadEnabled || !selectedFile}
          onClick={() => alert('CSV import will be implemented in a follow-up PR.')}
        >
          Upload CSV
        </Button>
      </Form>
    </Container>
  );
};
