import React from 'react';
import { Button, Container, Header } from 'semantic-ui-react';

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

  /* ------------------ UI ------------------ */

  return (
    <Container className="myopencre-container">
      <Header as="h1">MyOpenCRE</Header>

      <p>
        MyOpenCRE allows you to map your own security standard (e.g. SOC2) to OpenCRE Common Requirements
        using a CSV spreadsheet.
      </p>

      <p>
        Start by downloading the mapping template below, fill it with your standard’s controls, and map them
        to CRE IDs.
      </p>

      <Button primary onClick={downloadTemplate}>
        Download Mapping Template (CSV)
      </Button>
    </Container>
  );
};
