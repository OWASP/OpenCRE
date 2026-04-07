import './MyOpenCRE.scss';
import axios from 'axios';
import React, { useEffect, useState } from 'react';
import { Button, Container, Form, Header, Icon, Label, Loader, Message, Segment, Table } from 'semantic-ui-react';
import { useEnvironment } from '../../hooks';
import { ChangesetGraph } from './ChangesetGraph';

interface ImportRun {
  id: string;
  source: string;
  version: string | null;
  created_at: string;
  has_conflicts: boolean | null;
  staging_status: string | null;
}

export const MyOpenCRE = () => {
  const env = useEnvironment();
  const [config, setConfig] = useState<any>(null);
  const [runs, setRuns] = useState<ImportRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRun, setSelectedRun] = useState<ImportRun | null>(null);
  const [runDetails, setRunDetails] = useState<any>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<string>('');
  const [importLogs, setImportLogs] = useState<string[]>([]);

  const fetchConfig = async () => {
    try {
      const response = await axios.get(`${env.apiUrl}/config`);
      setConfig(response.data);
    } catch (e) {
      console.error(e);
      setConfig({ CRE_ALLOW_IMPORT: false });
    }
  };

  const fetchRuns = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${env.apiUrl}/../admin/imports/runs`);
      setRuns(response.data.runs || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  useEffect(() => {
    if (config?.CRE_ALLOW_IMPORT) {
      fetchRuns();
    }
  }, [config]);

  const handleRunSelect = async (run: ImportRun) => {
    setSelectedRun(run);
    setActionLoading(true);
    try {
      const [runRes, changesetRes, impactRes] = await Promise.all([
        axios.get(`${env.apiUrl}/../admin/imports/runs/${run.id}`),
        axios.get(`${env.apiUrl}/../admin/imports/runs/${run.id}/changeset`),
        axios.get(`${env.apiUrl}/../admin/imports/runs/${run.id}/impact`),
      ]);
      setRunDetails({
        ...runRes.data,
        changeset: changesetRes.data,
        impact: impactRes.data,
      });
    } catch (e) {
      console.error(e);
      setRunDetails(null);
    }
    setActionLoading(false);
  };

  const applyRun = async (runId: string) => {
    setActionLoading(true);
    try {
      await axios.post(`${env.apiUrl}/../admin/imports/runs/${runId}/apply`);
      await fetchRuns();
      setSelectedRun(null);
    } catch (e) {
      console.error(e);
      alert('Failed to apply changes.');
    }
    setActionLoading(false);
  };

  const discardRun = async (runId: string) => {
    setActionLoading(true);
    try {
      await axios.post(`${env.apiUrl}/../admin/imports/runs/${runId}/discard`);
      await fetchRuns();
      setSelectedRun(null);
    } catch (e) {
      console.error(e);
      alert('Failed to discard changes.');
    }
    setActionLoading(false);
  };

  const rerunImport = async (source: string) => {
    setUploadProgress(`Starting import for ${source}...`);
    setImportLogs((prev) => [...prev, `[${new Date().toISOString()}] Starting import for ${source}...`]);
    setActionLoading(true);
    try {
      const response = await axios.post(`${env.apiUrl}/../admin/imports/rerun`, { source });
      setImportLogs((prev) => [...prev, `[${new Date().toISOString()}] Import triggered successfully. Run ID: ${response.data.run_id}`]);
      setUploadProgress(`Import completed for ${source}`);
      await fetchRuns();
    } catch (e: any) {
      console.error(e);
      setImportLogs((prev) => [...prev, `[${new Date().toISOString()}] Import failed: ${e.message}`]);
      setUploadProgress('Import failed.');
    }
    setActionLoading(false);
  };

  const handleUploadCsv = async () => {
    if (!csvFile) return;
    const formData = new FormData();
    formData.append('cre_csv', csvFile);

    setUploadProgress('Uploading CSV...');
    setImportLogs((prev) => [...prev, `[${new Date().toISOString()}] Uploading CSV file: ${csvFile.name}`]);
    setActionLoading(true);

    try {
      const res = await axios.post(`${env.apiUrl}/cre_csv_import`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setImportLogs((prev) => [...prev, `[${new Date().toISOString()}] CSV upload successful. Processing...`]);
      setUploadProgress('CSV uploaded successfully!');
      await fetchRuns();
    } catch (e: any) {
      console.error(e);
      setImportLogs((prev) => [...prev, `[${new Date().toISOString()}] CSV upload failed: ${e.message}`]);
      setUploadProgress('Failed to upload CSV.');
    }
    setActionLoading(false);
  };

  if (config === null) return <Loader active />;
  if (!config.CRE_ALLOW_IMPORT) {
    return (
      <Container className="myopencre-container">
        <Message warning>
          <Message.Header>Import functionality is disabled</Message.Header>
          <p>Please set the CRE_ALLOW_IMPORT environment variable to True to enable MyOpenCRE.</p>
        </Message>
      </Container>
    );
  }

  return (
    <Container className="myopencre-container">
      <Header as="h1">MyOpenCRE - Imports Dashboard</Header>
      
      <Segment>
        <Header as="h3">Trigger New Import</Header>
        <Form>
          <Form.Group widths="equal">
            <Form.Input
              type="file"
              label="MyOpenCRE CSV File"
              onChange={(e: any) => setCsvFile(e.target.files[0])}
            />
          </Form.Group>
          <Button primary loading={actionLoading} onClick={handleUploadCsv} disabled={!csvFile}>
            Upload and Import CSV
          </Button>
          <Button secondary loading={actionLoading} onClick={() => rerunImport('master_spreadsheet')}>
            Rerun Master Spreadsheet
          </Button>
          <Button basic color="blue" loading={actionLoading} onClick={() => rerunImport('utilities')}>
            Rerun Utility Importers
          </Button>
        </Form>
        {uploadProgress && <Message info>{uploadProgress}</Message>}
        
        {importLogs.length > 0 && (
          <Segment inverted className="log-viewer">
            {importLogs.map((log, i) => (
              <div key={i}>{log}</div>
            ))}
          </Segment>
        )}
      </Segment>

      <Header as="h3">Staged Import Runs</Header>
      {loading ? (
        <Loader active />
      ) : (
        <Table celled striped>
          <Table.Header>
            <Table.Row>
              <Table.HeaderCell>Run ID</Table.HeaderCell>
              <Table.HeaderCell>Source</Table.HeaderCell>
              <Table.HeaderCell>Date</Table.HeaderCell>
              <Table.HeaderCell>Status</Table.HeaderCell>
              <Table.HeaderCell>Action</Table.HeaderCell>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {runs.map((run) => (
              <Table.Row key={run.id} active={selectedRun?.id === run.id}>
                <Table.Cell>{run.id}</Table.Cell>
                <Table.Cell>
                  {run.source}
                  {run.source !== 'myopencre_csv' && (
                    <Label color="yellow" size="small" style={{ marginLeft: '10px' }}>
                      legacy
                    </Label>
                  )}
                </Table.Cell>
                <Table.Cell>{new Date(run.created_at).toLocaleString()}</Table.Cell>
                <Table.Cell>
                  {run.staging_status}
                  {run.has_conflicts && <Label color="red">Conflicts</Label>}
                </Table.Cell>
                <Table.Cell>
                  <Button size="small" onClick={() => handleRunSelect(run)}>
                    View Details
                  </Button>
                </Table.Cell>
              </Table.Row>
            ))}
            {runs.length === 0 && (
              <Table.Row>
                <Table.Cell colSpan="5" textAlign="center">
                  No import runs found.
                </Table.Cell>
              </Table.Row>
            )}
          </Table.Body>
        </Table>
      )}

      {selectedRun && runDetails && (
        <Segment>
          <Header as="h3">Run Details: {selectedRun.id}</Header>
          <p>
            <strong>Source:</strong> {selectedRun.source}
          </p>
          <p>
            <strong>Status:</strong> {selectedRun.staging_status}
          </p>
          
          <Header as="h4">Changeset Summary</Header>
          {runDetails.changeset ? (
            <>
              <pre className="changeset-pre">{JSON.stringify(runDetails.changeset, null, 2)}</pre>
              <Header as="h4">Graph Visualization</Header>
              <ChangesetGraph runId={selectedRun.id} />
            </>
          ) : (
            <p>No changeset available.</p>
          )}

          <Header as="h4">Impact Summary</Header>
          {runDetails.impact ? (
            <pre className="impact-pre">{JSON.stringify(runDetails.impact, null, 2)}</pre>
          ) : (
            <p>No impact data available.</p>
          )}

          {selectedRun.staging_status === 'pending_review' && (
            <div style={{ marginTop: '20px' }}>
              <Button color="green" loading={actionLoading} onClick={() => applyRun(selectedRun.id)}>
                Apply Changes
              </Button>
              <Button color="red" loading={actionLoading} onClick={() => discardRun(selectedRun.id)}>
                Discard
              </Button>
            </div>
          )}
        </Segment>
      )}
    </Container>
  );
};
