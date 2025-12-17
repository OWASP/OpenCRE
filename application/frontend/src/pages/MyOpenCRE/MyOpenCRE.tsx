import './MyOpenCRE.scss';

import React, { useRef, useState } from 'react';
import { Button, Container, Form, Header, Message } from 'semantic-ui-react';

import { useEnvironment } from '../../hooks';

export const MyOpenCRE = () => {
  const { apiUrl } = useEnvironment();

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

      <p className="myopencre-intro">
        MyOpenCRE allows you to map your own security standard (e.g. SOC2) to OpenCRE Common Requirements
        using a CSV spreadsheet.
      </p>

      <p className="myopencre-intro">
        Start by downloading the CRE catalogue below, then map your standard’s controls or sections to CRE IDs
        in the spreadsheet.
      </p>
      <div className="myopencre-section">
        <Button primary onClick={downloadCreCsv}>
          Download CRE Catalogue (CSV)
        </Button>
      </div>

      <Button primary onClick={downloadTemplate}>
        Download Mapping Template (CSV)
      </Button>
    </Container>
  );
};
