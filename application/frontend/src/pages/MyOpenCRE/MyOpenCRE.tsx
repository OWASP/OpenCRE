import './MyOpenCRE.scss';

import React, { useState } from 'react';
import { Button, Container, Form, Header, Label, Loader, Message, Table } from 'semantic-ui-react';
import { useEnvironment } from '../../hooks';

export const MyOpenCRE = () => {
  const { apiUrl } = useEnvironment();
  const isUploadEnabled = apiUrl !== '/rest/v1';

  // CSV import state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<any | null>(null);

  // AI suggest state
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [mapped, setMapped] = useState<any[]>([]);
  const [needsReview, setNeedsReview] = useState<any[]>([]);
  const [suggestFileName, setSuggestFileName] = useState<string>('');

  const downloadCreCsv = async () => {
    try {
      const response = await fetch(`${apiUrl}/cre_csv`, {
        method: 'GET',
        headers: { Accept: 'text/csv' },
      });
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
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

  const downloadTemplate = () => {
    const headers = ['standard_name', 'standard_section', 'cre_id', 'notes'];
    const csvContent = headers.join(',') + '\n';
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'myopencre_mapping_template.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setImportError(null);
    setImportSuccess(null);
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setImportError('Please upload a valid CSV file.');
      e.target.value = '';
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
  };

  const uploadCsv = async () => {
    if (!selectedFile) return;
    setImportLoading(true);
    setImportError(null);
    setImportSuccess(null);
    const formData = new FormData();
    formData.append('cre_csv', selectedFile);
    try {
      const response = await fetch(`${apiUrl}/cre_csv_import`, {
        method: 'POST',
        body: formData,
      });
      if (response.status === 403) {
        throw new Error('CSV import is disabled on hosted environments. Run OpenCRE locally with CRE_ALLOW_IMPORT=true.');
      }
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || 'CSV import failed');
      }
      const result = await response.json();
      setImportSuccess(result);
      setSelectedFile(null);
    } catch (err: any) {
      setImportError(err.message || 'Unexpected error during import');
    } finally {
      setImportLoading(false);
    }
  };

  const handleSuggestUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSuggestFileName(file.name);
    setSuggestLoading(true);
    setSuggestError(null);
    setMapped([]);
    setNeedsReview([]);
    const formData = new FormData();
    formData.append('cre_csv', file);
    try {
      const response = await fetch(`${apiUrl}/suggest_cre_mappings`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) throw new Error(`Server error: ${response.status}`);
      const result = await response.json();
      setMapped(result.mapped || []);
      setNeedsReview(result.needs_review || []);
    } catch (err: any) {
      setSuggestError(err.message || 'An error occurred while processing your file.');
    } finally {
      setSuggestLoading(false);
    }
  };

  return (
    <Container style={{ marginTop: '3rem' }}>
      <Header as="h1">MyOpenCRE</Header>
      <p>
        MyOpenCRE allows you to map your own security standard (e.g. SOC2) to OpenCRE Common
        Requirements using a CSV spreadsheet.
      </p>

      <div className="myopencre-section">
        <Button primary onClick={downloadCreCsv}>
          Download CRE Catalogue (CSV)
        </Button>
        <Button secondary onClick={downloadTemplate} style={{ marginLeft: '1rem' }}>
          Download Mapping Template (CSV)
        </Button>
      </div>

      {/* AI Suggest Section */}
      <div className="myopencre-section" style={{ marginTop: '2rem' }}>
        <Header as="h3">AI-Suggested CRE Mappings</Header>
        <p>Upload your standard's CSV to get automatic CRE mapping suggestions powered by AI.</p>

        <Button as="label" htmlFor="suggest-upload" secondary>
          {suggestFileName ? `Uploaded: ${suggestFileName}` : 'Upload Standard for AI Suggestions'}
          <input id="suggest-upload" type="file" accept=".csv" hidden onChange={handleSuggestUpload} />
        </Button>

        {suggestLoading && <Loader active inline="centered" style={{ marginTop: '1rem' }} content="Analyzing your standard..." />}
        {suggestError && <Message negative style={{ marginTop: '1rem' }}><Message.Header>Error</Message.Header><p>{suggestError}</p></Message>}

        {mapped.length > 0 && (
          <>
            <Header as="h4" style={{ marginTop: '1.5rem' }}>
              Suggested Mappings <Label color="green">{mapped.length} matched</Label>
            </Header>
            <Table celled compact>
              <Table.Header>
                <Table.Row>
                  <Table.HeaderCell>Standard Section</Table.HeaderCell>
                  <Table.HeaderCell>Suggested CRE</Table.HeaderCell>
                  <Table.HeaderCell>Confidence</Table.HeaderCell>
                </Table.Row>
              </Table.Header>
              <Table.Body>
                {mapped.map((item, idx) => (
                  <Table.Row key={idx}>
                    <Table.Cell>{item.standard?.section || item.standard?.name}</Table.Cell>
                    <Table.Cell>
                      <a href={`/node/CRE/${item.suggested_cre_id}`} target="_blank" rel="noreferrer">
                        {item.suggested_cre_id}
                      </a>
                    </Table.Cell>
                    <Table.Cell>
                      <Label color={item.confidence >= 0.85 ? 'green' : 'yellow'}>
                        {(item.confidence * 100).toFixed(1)}%
                      </Label>
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
          </>
        )}

        {needsReview.length > 0 && (
          <>
            <Header as="h4" style={{ marginTop: '1.5rem' }}>
              Needs Review <Label color="orange">{needsReview.length} items</Label>
            </Header>
            <p>These controls could not be automatically mapped and require manual review.</p>
            <Table celled compact>
              <Table.Header>
                <Table.Row>
                  <Table.HeaderCell>Standard Section</Table.HeaderCell>
                  <Table.HeaderCell>Description</Table.HeaderCell>
                </Table.Row>
              </Table.Header>
              <Table.Body>
                {needsReview.map((item, idx) => (
                  <Table.Row key={idx}>
                    <Table.Cell>{item.standard?.section || item.standard?.name}</Table.Cell>
                    <Table.Cell>{item.standard?.description || '—'}</Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
          </>
        )}
      </div>

      {/* CSV Import Section */}
      <div className="myopencre-section myopencre-upload" style={{ marginTop: '2rem' }}>
        <Header as="h3">Import Standard into OpenCRE</Header>
        <p>Upload your completed mapping spreadsheet to import your standard into OpenCRE.</p>

        {!isUploadEnabled && (
          <Message info className="myopencre-disabled">
            CSV upload is disabled on hosted environments. Run OpenCRE locally with CRE_ALLOW_IMPORT=true.
          </Message>
        )}
        {importError && <Message negative>{importError}</Message>}
        {importSuccess && (
          <Message positive>
            <strong>Import successful</strong>
            <ul>
              <li>New CREs added: {importSuccess.new_cres?.length ?? 0}</li>
              <li>Standards imported: {importSuccess.new_standards}</li>
            </ul>
          </Message>
        )}

        <Form>
          <Form.Field>
            <input type="file" accept=".csv" disabled={!isUploadEnabled || importLoading} onChange={onFileChange} />
          </Form.Field>
          <Button primary loading={importLoading} disabled={!isUploadEnabled || !selectedFile || importLoading} onClick={uploadCsv}>
            Upload CSV
          </Button>
        </Form>
      </div>
    </Container>
  );
};