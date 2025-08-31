import './myopencre.scss';

import React, { useEffect, useState } from 'react';
import { Button, Container, Divider, Form, Grid, Header, Icon, Message, Segment } from 'semantic-ui-react';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';

export const MyOpenCRE = () => {
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  const [suggestionFile, setSuggestionFile] = useState<File | null>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importSuccess, setImportSuccess] = useState<string>('');

  // NEW: Robust handler for the template download
  const handleTemplateDownload = () => {
    setLoading(true);
    setError('');
    setImportSuccess('');

    fetch(`${apiUrl}/cre_csv`, {})
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Server responded with status: ${response.status}`);
        }
        return response.blob();
      })
      .then((blob) => {
        setLoading(false);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'CRE-Catalogue.csv'; // The correct filename from the backend
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      })
      .catch((err) => {
        setLoading(false);
        setError(`Failed to download template: ${err.message}`);
      });
  };

  // Handlers for the AI Suggestion form
  const handleSuggestionFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      setSuggestionFile(event.target.files[0]);
    }
  };

  const handleSuggestionUpload = (event: React.FormEvent) => {
    event.preventDefault();
    if (!suggestionFile) return;

    setLoading(true);
    setError('');
    setImportSuccess('');

    const formData = new FormData();
    formData.append('cre_csv', suggestionFile);

    fetch(`${apiUrl}/cre_csv/suggest`, {
      method: 'POST',
      body: formData,
    })
      .then((response) => response.blob())
      .then((blob) => {
        setLoading(false);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'cre-suggestions.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      })
      .catch((err) => {
        setLoading(false);
        setError(`Failed to analyze file: ${err.message}`);
      });
  };

  const handleImportFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      setImportFile(event.target.files[0]);
    }
  };

  const handleFullImport = (event: React.FormEvent) => {
    event.preventDefault();
    if (!importFile) return;

    setLoading(true);
    setError('');
    setImportSuccess('');

    const formData = new FormData();
    formData.append('cre_csv', importFile);

    fetch(`${apiUrl}/cre_csv_import`, {
      method: 'POST',
      body: formData,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Server error: ${response.status}`);
        return response.json();
      })
      .then((data) => {
        setLoading(false);
        setImportSuccess(
          `Successfully imported! New CREs: ${data.new_cres.length}, New Standards: ${data.new_standards}`
        );
        if ('Notification' in window && Notification.permission === 'granted') {
          new Notification('OpenCRE Import Complete', { body: 'Your new mappings have been processed.' });
        }
      })
      .catch((err) => {
        setLoading(false);
        setError(`Import failed: ${err.message}`);
      });
  };

  // Request notification permission on component mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission !== 'granted') {
      Notification.requestPermission();
    }
  }, []);

  return (
    <div className="myopencre-page-container">
      <Grid textAlign="center" verticalAlign="middle">
        <Grid.Column style={{ maxWidth: 700 }}>
          <Header as="h1" icon textAlign="center" className="page-header">
            <Icon name="sync alternate" circular />
            <Header.Content>MyOpenCRE Workspace</Header.Content>
          </Header>

          {/* Section 1: Download Template */}
          <Segment padded="very" className="workspace-segment">
            <Header as="h2" icon="download" content="Step 1: Get the Template" />
            <p>
              Download the complete, up-to-date list of all CREs. Use this file to map your own security
              standards by filling in the standard-related columns for each CRE.
            </p>
            {/* UPDATED: This is now a standard button with an onClick handler */}
            <Button onClick={handleTemplateDownload} primary size="large" loading={loading}>
              <Icon name="download" /> Download CRE Mapping Template
            </Button>
          </Segment>

          {/* Section 2: AI Suggestions (Feature Flagged) */}
          {process.env.REACT_APP_ENABLE_AI_SUGGESTIONS === 'true' && (
            <Segment padded="very" className="workspace-segment">
              <Header as="h2" icon="magic" content="Step 2 (Optional): Get AI Suggestions" />
              <p>
                Have a CSV with descriptions but missing CREs? Upload it here, and our AI will analyze it and
                return a new file with high-confidence mapping suggestions.
              </p>
              <Form onSubmit={handleSuggestionUpload}>
                <Form.Input
                  type="file"
                  label="Select a .csv File for Analysis"
                  accept=".csv"
                  onChange={handleSuggestionFileChange}
                />
                <Button fluid size="large" type="submit" disabled={!suggestionFile || loading} color="teal">
                  <Icon name="cogs" /> Analyze and Download Suggestions
                </Button>
              </Form>
            </Segment>
          )}

          {/* Section 3: Final Import (Feature Flagged) */}
          {process.env.REACT_APP_ENABLE_FULL_IMPORT === 'true' && (
            <Segment padded="very" className="workspace-segment">
              <Header as="h2" icon="upload" content="Step 3: Import Your Mappings" />
              <p>
                Once your spreadsheet is complete, upload it here to import your new standard mappings into
                the OpenCRE database.
              </p>
              <Form onSubmit={handleFullImport}>
                <Form.Input
                  type="file"
                  label="Select a .csv File to Import"
                  accept=".csv"
                  onChange={handleImportFileChange}
                />
                <Button fluid size="large" type="submit" disabled={!importFile || loading} color="green">
                  <Icon name="upload" /> Upload and Import to OpenCRE
                </Button>
              </Form>
            </Segment>
          )}

          {/* Indicator section for loading, errors, and success messages */}
          <div className="indicator-container">
            <LoadingAndErrorIndicator loading={loading} error={error} />
            {importSuccess && !error && (
              <Message positive header="Import Successful" content={importSuccess} />
            )}
          </div>
        </Grid.Column>
      </Grid>
    </div>
  );
};
