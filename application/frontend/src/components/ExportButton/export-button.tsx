import './export-button.scss';

import React, { useState } from 'react';
import { Loader } from 'semantic-ui-react';

interface IExportButton {
  fetchURL: string;
  fetchParams?: string[][];
}

const openURLInNewTab = (url: string): void => {
  const newWindow = window.open(url, '_blank', 'noopener,noreferrer');
  if (newWindow) newWindow.opener = null;
};

/**
 * Returns the export URL for a given API endpoint.
 * Handles the CRE, search and standard endpoints.
 *
 * Also handles query parameters as part of the `url` or as part of `params`.
 * @param url original fetch URL
 * @param params (optional) parameters that were passed to Axios
 * @returns computed request url to get an export of the endpoint
 */
const getExportURL = (url: string, params?: string[][]): string => {
  const EXPORT_STRING = '/export';
  if (url.includes('?')) {
    const [prefix, queryParams] = url.split('?');
    return prefix + EXPORT_STRING + '?' + queryParams;
  }

  if (params) {
    return url + '/export?' + new URLSearchParams(params['params']).toString();
  }

  return url + EXPORT_STRING;
};

const ExportButton = ({ fetchURL, fetchParams }: IExportButton) => {
  const [isLoading, setLoading] = useState(false);

  const fetchSpreadsheetURLAndOpen = () => {
    setLoading(true);

    fetch(getExportURL(fetchURL, fetchParams))
      .then((response) => response.json())
      .then((data) => {
        if (!data || !data.status || data.status !== 'ok') {
          window.alert('Failed to export CRE data');
        }

        openURLInNewTab(data.spreadsheetURL);

        // Timeout is added so we don't get a flashing effect
        setTimeout(() => {
          setLoading(false);
        }, 500);
      });
  };

  return (
    <a role="button" className="export-button" onClick={() => fetchSpreadsheetURLAndOpen()}>
      🔗 Export
      {isLoading && (
        <>
          {' '}
          <Loader inline size="mini" active={isLoading} />
        </>
      )}
    </a>
  );
};

export default ExportButton;
