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
