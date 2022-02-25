import './export-button.scss';

import React, { useState } from 'react';
import { Loader } from 'semantic-ui-react';

interface IExportButton {
  fetchURL: string;
}

export const openURLInNewTab = (url: string): void => {
  const newWindow = window.open(url, '_blank', 'noopener,noreferrer');
  if (newWindow) newWindow.opener = null;
};

const ExportButton = ({ fetchURL }: IExportButton) => {
  const [isLoading, setLoading] = useState(false);

  const fetchSpreadsheetURLAndOpen = () => {
    setLoading(true);

    fetch(fetchURL + '/export')
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
