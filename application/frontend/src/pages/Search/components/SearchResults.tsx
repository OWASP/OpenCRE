import React from 'react';

import { DocumentNode } from '../../../components/DocumentNode';
import { getDocumentDisplayName } from 'application/frontend/src/utils/document';

export const SearchResults = ({ results }) => {
  if (results && results.length != 0) {
    return (
      <>
        {results.sort((a, b) => getDocumentDisplayName(a).localeCompare(getDocumentDisplayName(b))).map((document, i) => (
          <div key={i} className="accordion ui fluid styled standard-page__links-container">
            <DocumentNode node={document} linkType={'Standard'} />
          </div>
        ))}
      </>
    );
  }
  return <></>;
};
