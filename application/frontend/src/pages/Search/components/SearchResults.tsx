import { DOCUMENT_TYPES } from 'application/frontend/src/const';
import { getDocumentDisplayName } from 'application/frontend/src/utils/document';
import React from 'react';

import { DocumentNode } from '../../../components/DocumentNode';

export const SearchResults = ({ results }) => {
  if (results && results.length != 0) {
    const sortedResults = results.sort((a, b) =>
      getDocumentDisplayName(a).localeCompare(getDocumentDisplayName(b))
    );
    let lastDocumentName = sortedResults[0].name;
    return (
      <>
        {sortedResults.map((document, i) => {
          let temp = (
            <>
              {document.doctype != DOCUMENT_TYPES.TYPE_CRE && lastDocumentName !== document.name && (
                <span style={{ margin: '5px' }} />
              )}
              <div key={i} className="accordion ui fluid styled standard-page__links-container">
                <DocumentNode node={document} linkType={'Standard'} />
              </div>
            </>
          );
          lastDocumentName = document.id ?? document.name;
          return temp;
        })}
      </>
    );
  }
  return <></>;
};
