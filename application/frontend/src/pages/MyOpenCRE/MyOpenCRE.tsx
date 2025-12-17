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
  /* ------------------ CSV UPLOAD ------------------ */

  const uploadCsv = async () => {
    if (!selectedFile || !confirmedImport) return;

    setLoading(true);
    setError(null);
    setSuccess(null);
    setInfo(null);

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
      } else if (payload.import_type === 'empty') {
        setInfo('The uploaded CSV did not contain any importable rows. No changes were made.');
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
