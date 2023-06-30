import React from 'react';

import { DocumentNode } from '../../../components/DocumentNode';
import { getDocumentDisplayName } from 'application/frontend/src/utils/document';

export const SearchResults = ({ results }) => {
  if (results && results.length != 0) {
    const sortedResults = results.sort((a, b) => getDocumentDisplayName(a).localeCompare(getDocumentDisplayName(b)))
    let lastDocumentName = sortedResults[0].id ?? sortedResults[0].name
    return (
      <>
        {sortedResults.map((document, i) => (
          <>
            {lastDocumentName !== (document.id ?? document.name) &&<hr style={{marginTop: "20px"}} />}
            <div key={i} className="accordion ui fluid styled standard-page__links-container">
              <DocumentNode node={document} linkType={'Standard'} />
            </div>
          </>
        ))}
      </>
    );
  }
  return <></>;
};
