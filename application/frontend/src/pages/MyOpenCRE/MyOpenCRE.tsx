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

  return (
    <Container className="myopencre-container">
      <Header as="h1">MyOpenCRE</Header>

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
