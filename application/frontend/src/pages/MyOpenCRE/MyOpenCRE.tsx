import React from 'react';
import { Button, Container, Header } from 'semantic-ui-react';

import { useEnvironment } from '../../hooks';

export const MyOpenCRE = () => {
  const { apiUrl } = useEnvironment();
  // console.log('API URL:', apiUrl);

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

  return (
    <Container style={{ marginTop: '3rem' }}>
      <Header as="h1">MyOpenCRE</Header>

      <p>
        MyOpenCRE allows you to map your own security standard (e.g. SOC2) to OpenCRE Common Requirements
        using a CSV spreadsheet.
      </p>

      <p>
        Start by downloading the mapping template below, fill it with your standard’s controls, and map them
        to CRE IDs.
      </p>

      <Button primary onClick={downloadCreCsv}>
        Download CRE Catalogue (CSV)
      </Button>
    </Container>
  );
};
